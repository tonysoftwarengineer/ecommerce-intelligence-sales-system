"""Process-local cache of verified grounded answers, keyed by question and evidence content."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Iterable
from threading import RLock
from typing import Callable

from src.rag.answers import (
    ProviderGeneration,
    build_grounded_answer_prompt,
)
from src.rag.contracts import RetrievedEvidence


def answer_cache_key(
    provider: str,
    model: str,
    max_output_tokens: int,
    question: str,
    evidence: tuple[RetrievedEvidence, ...],
) -> str:
    """Hash everything that determines a provider answer, except per-upload IDs.

    Chunk IDs embed each upload's random document ID, so the same file uploaded
    twice gets different IDs. The key replaces them with positions and hashes
    the resulting prompt: question, instructions, excerpt text, and citations
    (filename, version, section). A hit therefore requires word-for-word
    identical excerpts in the same order, which the caller already holds, so
    sharing an entry across guests discloses nothing new.
    """
    system_instruction, user_payload = build_grounded_answer_prompt(
        question, _positional_evidence(evidence)
    )
    material = json.dumps(
        [provider, model, max_output_tokens, system_instruction, user_payload],
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _placeholder(index: int) -> str:
    return f"evidence-{index + 1}"


def _positional_evidence(
    evidence: tuple[RetrievedEvidence, ...],
) -> tuple[RetrievedEvidence, ...]:
    return tuple(
        dataclasses.replace(item, chunk_id=_placeholder(index))
        for index, item in enumerate(evidence)
    )


def _remap_chunk_ids(payload: object, mapping: dict[str, str]) -> object:
    """Copy a provider payload, translating claim chunk IDs; unknown IDs are kept."""
    portable = copy.deepcopy(payload)
    if isinstance(portable, dict) and isinstance(portable.get("claims"), list):
        for claim in portable["claims"]:
            if isinstance(claim, dict) and isinstance(claim.get("chunk_id"), str):
                claim["chunk_id"] = mapping.get(claim["chunk_id"], claim["chunk_id"])
    return portable


def to_portable(payload: object, evidence: tuple[RetrievedEvidence, ...]) -> object:
    """Replace this upload's chunk IDs with positions before caching."""
    return _remap_chunk_ids(
        payload, {item.chunk_id: _placeholder(index) for index, item in enumerate(evidence)}
    )


def from_portable(payload: object, evidence: tuple[RetrievedEvidence, ...]) -> object:
    """Map positions back to the current request's chunk IDs before verification."""
    return _remap_chunk_ids(
        payload, {_placeholder(index): item.chunk_id for index, item in enumerate(evidence)}
    )


class RagAnswerCache:
    """Bounded LRU with a time-to-live. Stores provider payloads, never guest IDs."""

    def __init__(
        self,
        max_entries: int = 256,
        ttl_seconds: float = 24 * 60 * 60,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least one")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.monotonic
        self._entries: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._source_documents: dict[str, set[str]] = {}
        self._lock = RLock()

    def get(self, key: str, source_document_ids: Iterable[str]) -> object | None:
        document_ids = set(source_document_ids)
        if not document_ids:
            raise ValueError("A cached answer must have source documents")
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, payload = entry
            if now - stored_at >= self._ttl_seconds:
                self._remove(key)
                return None
            self._source_documents[key].update(document_ids)
            self._entries.move_to_end(key)
            return payload

    def put(self, key: str, payload: object, source_document_ids: Iterable[str]) -> None:
        document_ids = set(source_document_ids)
        if not document_ids:
            raise ValueError("A cached answer must have source documents")
        with self._lock:
            self._entries[key] = (self._clock(), payload)
            self._source_documents.setdefault(key, set()).update(document_ids)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                oldest = next(iter(self._entries))
                self._remove(oldest)

    def invalidate_documents(self, document_ids: Iterable[str]) -> int:
        """Discard answers supported by any deleted or superseded document."""
        removed_ids = set(document_ids)
        with self._lock:
            stale = [
                key
                for key, sources in self._source_documents.items()
                if not sources.isdisjoint(removed_ids)
            ]
            for key in stale:
                self._remove(key)
            return len(stale)

    def cleanup_stale(self, active_document_ids: Iterable[str]) -> int:
        """Remove expired entries and answers whose sources are no longer active."""
        active_ids = set(active_document_ids)
        now = self._clock()
        with self._lock:
            stale = [
                key
                for key, (stored_at, _) in self._entries.items()
                if now - stored_at >= self._ttl_seconds
                or not self._source_documents[key].issubset(active_ids)
            ]
            for key in stale:
                self._remove(key)
            return len(stale)

    def _remove(self, key: str) -> None:
        self._entries.pop(key, None)
        self._source_documents.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._source_documents.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


class ReplayAnswerProvider:
    """Return a cached payload, remapped to the current chunk IDs, for normal verification."""

    configured = True

    def __init__(self, name: str, model: str, payload: object) -> None:
        self.name = name
        self.model = model
        self._payload = payload

    def generate(self, question, evidence) -> ProviderGeneration:
        return ProviderGeneration(payload=from_portable(self._payload, evidence))


class RecordingAnswerProvider:
    """Wrap a real provider and keep its raw payload so a verified answer can be cached."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.name = inner.name
        self.model = inner.model
        self.configured = getattr(inner, "configured", True)
        self.payload: object | None = None

    def generate(self, question, evidence):
        generation = self._inner.generate(question, evidence)
        self.payload = (
            generation.payload if isinstance(generation, ProviderGeneration) else generation
        )
        return generation
