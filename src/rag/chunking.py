import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from src.rag.contracts import RagChunk, RagDocument

TOKEN_PATTERN = re.compile(r"\w+(?:['’-]\w+)*|[^\w\s]", re.UNICODE)
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class ChunkingConfig:
    max_tokens: int = 192
    overlap_tokens: int = 32

    def __post_init__(self) -> None:
        if self.max_tokens < 32:
            raise ValueError("max_tokens must be at least 32")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")


def tokenize(text: str) -> list[str]:
    """A deterministic token approximation used only for chunk boundaries."""
    return TOKEN_PATTERN.findall(text)


def chunk_document(document: RagDocument, config: ChunkingConfig) -> tuple[RagChunk, ...]:
    raw_chunks: list[tuple[Optional[str], str]] = []
    for heading, paragraphs in _sections(document.text):
        for paragraph in paragraphs:
            raw_chunks.extend((heading, value) for value in _split_paragraph(paragraph, config))

    chunks = []
    for index, (heading, text) in enumerate(raw_chunks):
        normalized = _normalize(text)
        identity = "|".join(
            (
                document.metadata.document_id,
                str(document.metadata.version),
                str(index),
                heading or "",
                normalized,
            )
        )
        chunks.append(
            RagChunk(
                chunk_id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                owner_scope_id=document.metadata.owner_scope_id,
                analysis_id=document.metadata.analysis_id,
                document_id=document.metadata.document_id,
                document_version=document.metadata.version,
                document_type=document.metadata.document_type,
                filename=document.metadata.filename,
                heading=heading,
                text=normalized,
                chunk_index=index,
            )
        )
    return tuple(chunks)


def _sections(text: str) -> list[tuple[Optional[str], list[str]]]:
    sections: list[tuple[Optional[str], list[str]]] = []
    heading: Optional[str] = None
    paragraph_lines: list[str] = []
    paragraphs: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            value = _normalize(" ".join(paragraph_lines))
            if value:
                paragraphs.append(value)
            paragraph_lines.clear()

    def flush_section() -> None:
        nonlocal paragraphs
        flush_paragraph()
        if paragraphs:
            sections.append((heading, paragraphs))
            paragraphs = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        match = HEADING_PATTERN.match(line)
        if match:
            flush_section()
            heading = match.group(2).strip()
        elif not line:
            flush_paragraph()
        else:
            paragraph_lines.append(line)
    flush_section()
    return sections


def _split_paragraph(paragraph: str, config: ChunkingConfig) -> list[str]:
    if len(tokenize(paragraph)) <= config.max_tokens:
        return [paragraph]

    sentences = [part.strip() for part in SENTENCE_PATTERN.split(paragraph) if part.strip()]
    if len(sentences) <= 1:
        return _token_windows(paragraph, config)

    chunks: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        if len(tokenize(sentence)) > config.max_tokens:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.extend(_token_windows(sentence, config))
            continue
        candidate = " ".join((*current, sentence))
        if current and len(tokenize(candidate)) > config.max_tokens:
            completed = " ".join(current)
            chunks.append(completed)
            sentence_tokens = tokenize(sentence)
            available_overlap = max(0, config.max_tokens - len(sentence_tokens))
            overlap_count = min(config.overlap_tokens, available_overlap)
            overlap = tokenize(completed)[-overlap_count:] if overlap_count else []
            current = [" ".join(overlap), sentence] if overlap else [sentence]
        else:
            current.append(sentence)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _token_windows(text: str, config: ChunkingConfig) -> list[str]:
    tokens = tokenize(text)
    step = config.max_tokens - config.overlap_tokens
    return [
        " ".join(tokens[start : start + config.max_tokens])
        for start in range(0, len(tokens), step)
    ]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
