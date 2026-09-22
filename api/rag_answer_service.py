import json
import re
from typing import Optional

import httpx

from config import (
    GEMINI_API_KEY,
    RAG_ANSWER_MODEL,
    RAG_ANSWER_PROVIDER,
    RAG_ANSWER_TIMEOUT_SECONDS,
)
from src.rag.answers import (
    ANSWER_JSON_SCHEMA,
    AnswerProviderError,
    GroundedAnswerProvider,
    build_grounded_answer_prompt,
)
from src.rag.contracts import RetrievedEvidence


class GeminiRestAnswerProvider:
    name = "gemini_rest"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client

    def generate(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> object:
        if not self.api_key:
            raise AnswerProviderError("Gemini API key is not configured")
        system_instruction, user_payload = build_grounded_answer_prompt(question, evidence)
        body = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_payload}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": ANSWER_JSON_SCHEMA,
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
        try:
            if self._client is None:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        url,
                        headers={"x-goog-api-key": self.api_key},
                        json=body,
                    )
            else:
                response = self._client.post(
                    url,
                    headers={"x-goog-api-key": self.api_key},
                    json=body,
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(str(part.get("text", "")) for part in parts)
            return json.loads(text)
        except httpx.HTTPStatusError as exc:
            raise AnswerProviderError(
                "Gemini answer generation failed",
                reason_code=f"gemini_http_{exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise AnswerProviderError(
                "Gemini answer generation failed", reason_code="gemini_request_failed"
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AnswerProviderError(
                "Gemini answer generation failed", reason_code="gemini_invalid_provider_response"
            ) from exc


class UnavailableAnswerProvider:
    name = "unavailable"

    def __init__(self, model: str) -> None:
        self.model = model

    def generate(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> object:
        raise AnswerProviderError("Grounded answer provider is not configured")


class DeterministicFakeAnswerProvider:
    """Explicit test-only provider used by CI and browser journeys."""

    name = "deterministic_fake"
    model = "extractive-test-provider"

    def generate(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> object:
        candidates = tuple(
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", evidence[0].excerpt.strip())
            if sentence.strip()
            and not sentence.lstrip().startswith("#")
            and len(sentence.strip()) <= 320
        )
        question_terms = set(re.findall(r"[a-z0-9]+", question.lower()))
        quote = max(
            candidates,
            key=lambda sentence: (
                len(question_terms & set(re.findall(r"[a-z0-9]+", sentence.lower()))),
                len(sentence),
            ),
            default=evidence[0].excerpt[:320].strip(),
        )
        return {
            "claims": [
                {
                    "claim": quote,
                    "chunk_id": evidence[0].chunk_id,
                    "supporting_quote": quote,
                }
            ]
        }


def build_answer_provider() -> GroundedAnswerProvider:
    if RAG_ANSWER_PROVIDER == "fake":
        return DeterministicFakeAnswerProvider()
    if RAG_ANSWER_PROVIDER != "gemini":
        raise ValueError("RAG_ANSWER_PROVIDER must be 'gemini' or 'fake'")
    if not GEMINI_API_KEY:
        return UnavailableAnswerProvider(RAG_ANSWER_MODEL)
    return GeminiRestAnswerProvider(
        api_key=GEMINI_API_KEY,
        model=RAG_ANSWER_MODEL,
        timeout_seconds=RAG_ANSWER_TIMEOUT_SECONDS,
    )


answer_provider = build_answer_provider()
