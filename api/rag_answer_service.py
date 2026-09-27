import json
import re
from typing import Optional

import httpx

from config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    RAG_ANSWER_MAX_OUTPUT_TOKENS,
    RAG_ANSWER_MODEL,
    RAG_ANSWER_PROVIDER,
    RAG_ANSWER_TIMEOUT_SECONDS,
)
from src.rag.answers import (
    ANSWER_JSON_SCHEMA,
    AnswerProviderError,
    AnswerTokenUsage,
    GroundedAnswerProvider,
    ProviderGeneration,
    build_grounded_answer_prompt,
)
from src.rag.contracts import RetrievedEvidence


class GeminiRestAnswerProvider:
    name = "gemini_rest"
    configured = True

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int = RAG_ANSWER_MAX_OUTPUT_TOKENS,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self._client = client

    def generate(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> ProviderGeneration:
        if not self.api_key:
            raise AnswerProviderError("Gemini API key is not configured")
        system_instruction, user_payload = build_grounded_answer_prompt(question, evidence)
        body = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_payload}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self.max_output_tokens,
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
            return ProviderGeneration(
                payload=json.loads(text),
                usage=_gemini_usage(payload.get("usageMetadata")),
            )
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


class GroqRestAnswerProvider:
    """Groq Chat Completions adapter for verified structured grounded answers."""

    name = "groq_rest"
    configured = True

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int = RAG_ANSWER_MAX_OUTPUT_TOKENS,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self._client = client

    def generate(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> ProviderGeneration:
        if not self.api_key:
            raise AnswerProviderError("Groq API key is not configured")
        system_instruction, user_payload = build_grounded_answer_prompt(question, evidence)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_payload},
            ],
            # Groq treats zero as the closest representable positive value.
            "temperature": 1e-8,
            "max_completion_tokens": self.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "grounded_answer",
                    "strict": True,
                    "schema": ANSWER_JSON_SCHEMA,
                },
            },
        }
        try:
            if self._client is None:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=body,
                    )
            else:
                response = self._client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
            text = payload["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                raise TypeError("Groq response content must be text")
            return ProviderGeneration(
                payload=json.loads(text),
                usage=_groq_usage(payload.get("usage")),
            )
        except httpx.HTTPStatusError as exc:
            raise AnswerProviderError(
                "Groq answer generation failed",
                reason_code=f"groq_http_{exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise AnswerProviderError(
                "Groq answer generation failed", reason_code="groq_request_failed"
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AnswerProviderError(
                "Groq answer generation failed", reason_code="groq_invalid_provider_response"
            ) from exc


class UnavailableAnswerProvider:
    name = "unavailable"
    configured = False

    def __init__(self, model: str) -> None:
        self.model = model

    def generate(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> ProviderGeneration:
        raise AnswerProviderError("Grounded answer provider is not configured")


class DeterministicFakeAnswerProvider:
    """Explicit test-only provider used by CI and browser journeys."""

    name = "deterministic_fake"
    model = "extractive-test-provider"
    configured = True

    def generate(
        self,
        question: str,
        evidence: tuple[RetrievedEvidence, ...],
    ) -> ProviderGeneration:
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
        return ProviderGeneration(
            payload={
                "claims": [
                    {
                        "claim": quote,
                        "chunk_id": evidence[0].chunk_id,
                        "supporting_quote": quote,
                    }
                ]
            }
        )


def build_answer_provider() -> GroundedAnswerProvider:
    if RAG_ANSWER_PROVIDER == "fake":
        return DeterministicFakeAnswerProvider()
    if RAG_ANSWER_PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            return UnavailableAnswerProvider(RAG_ANSWER_MODEL)
        return GeminiRestAnswerProvider(
            api_key=GEMINI_API_KEY,
            model=RAG_ANSWER_MODEL,
            timeout_seconds=RAG_ANSWER_TIMEOUT_SECONDS,
            max_output_tokens=RAG_ANSWER_MAX_OUTPUT_TOKENS,
        )
    if RAG_ANSWER_PROVIDER == "groq":
        if not GROQ_API_KEY:
            return UnavailableAnswerProvider(RAG_ANSWER_MODEL)
        return GroqRestAnswerProvider(
            api_key=GROQ_API_KEY,
            model=RAG_ANSWER_MODEL,
            timeout_seconds=RAG_ANSWER_TIMEOUT_SECONDS,
            max_output_tokens=RAG_ANSWER_MAX_OUTPUT_TOKENS,
        )
    raise ValueError("RAG_ANSWER_PROVIDER must be 'gemini', 'groq', or 'fake'")


def provider_is_configured(provider: GroundedAnswerProvider) -> bool:
    """Whether this provider can make an external or deterministic answer attempt.

    Test doubles written before this flag existed remain configured by default.
    """

    return bool(getattr(provider, "configured", True))


answer_provider = build_answer_provider()


def _gemini_usage(value: object) -> Optional[AnswerTokenUsage]:
    if not isinstance(value, dict):
        return None
    return _usage(
        value.get("promptTokenCount"),
        value.get("candidatesTokenCount"),
        value.get("totalTokenCount"),
    )


def _groq_usage(value: object) -> Optional[AnswerTokenUsage]:
    if not isinstance(value, dict):
        return None
    return _usage(
        value.get("prompt_tokens"),
        value.get("completion_tokens"),
        value.get("total_tokens"),
    )


def _usage(
    input_tokens: object,
    output_tokens: object,
    total_tokens: object,
) -> Optional[AnswerTokenUsage]:
    values = (input_tokens, output_tokens, total_tokens)
    if not all(isinstance(value, int) and value >= 0 for value in values):
        return None
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert isinstance(total_tokens, int)
    if input_tokens + output_tokens > total_tokens:
        return None
    return AnswerTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
