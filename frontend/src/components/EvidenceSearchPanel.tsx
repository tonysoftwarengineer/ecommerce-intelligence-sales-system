import { useEffect, useRef, useState } from "react";

import { fetchRagDocuments, getGroundedRagAnswer, uploadRagDocument } from "../api";
import type {
  RagAnswerResponse,
  RagDocumentMetadata,
  RagDocumentType,
} from "../types";

interface EvidenceSearchPanelProps {
  analysisId: string;
}

const DOCUMENT_TYPES: Array<{ value: RagDocumentType; label: string }> = [
  { value: "policy", label: "Policy" },
  { value: "supplier_notice", label: "Supplier notice" },
  { value: "product_catalog", label: "Product catalog" },
  { value: "operating_calendar", label: "Operating calendar" },
  { value: "other_approved", label: "Other approved document" },
];

export function EvidenceSearchPanel({ analysisId }: EvidenceSearchPanelProps) {
  const [documents, setDocuments] = useState<RagDocumentMetadata[]>([]);
  const [documentType, setDocumentType] = useState<RagDocumentType>("policy");
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<RagAnswerResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    fetchRagDocuments(analysisId)
      .then((response) => {
        if (active) setDocuments(response.documents);
      })
      .catch((reason: unknown) => {
        if (active) setError(messageFrom(reason));
      });
    return () => {
      active = false;
    };
  }, [analysisId]);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const created = await uploadRagDocument(analysisId, file, documentType);
      setDocuments((current) => [
        ...current.map((item) =>
          item.filename === created.filename && item.active_for_retrieval
            ? {
                ...item,
                index_status: "superseded" as const,
                active_for_retrieval: false,
                superseded_by_document_id: created.document_id,
              }
            : item,
        ),
        created,
      ]);
      setFile(null);
      setResult(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setUploading(false);
    }
  }

  async function requestGroundedAnswer() {
    const normalizedQuestion = question.trim();
    if (normalizedQuestion.length < 3) return;
    setSearching(true);
    setError(null);
    try {
      setResult(await getGroundedRagAnswer(analysisId, normalizedQuestion));
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setSearching(false);
    }
  }

  function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void requestGroundedAnswer();
  }

  const activeDocuments = documents.filter((item) => item.active_for_retrieval);

  return (
    <section className="evidence-search card" aria-labelledby="evidence-search-title">
      <div className="card__head evidence-search__head">
        <div>
          <p className="eyebrow">RAG Phase 2 · grounded answers</p>
          <h2 id="evidence-search-title">Ask approved business documents</h2>
          <p className="card__sub">
            AI answers use only retrieved approved-document excerpts. They do not calculate sales or forecasts.
          </p>
        </div>
        <span className="quality-badge quality-badge--experimental">experimental</span>
      </div>

      <div className="evidence-search__upload">
        <label>
          <span>Approved document type</span>
          <select value={documentType} onChange={(event) => setDocumentType(event.target.value as RagDocumentType)}>
            {DOCUMENT_TYPES.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>UTF-8 text or Markdown file</span>
          <input
            id="rag-document-file"
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button className="button button--secondary" type="button" disabled={!file || uploading} onClick={handleUpload}>
          {uploading ? "Indexing…" : "Upload and index"}
        </button>
      </div>

      <div className="evidence-search__scope" aria-live="polite">
        <strong>{activeDocuments.length} active latest document{activeDocuments.length === 1 ? "" : "s"}</strong>
        <span>Only documents approved for this analysis are searched.</span>
        {activeDocuments.length > 0 ? (
          <ul>
            {activeDocuments.map((document) => (
              <li key={document.document_id}>
                {document.filename} · version {document.version} · searchable
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <form className="evidence-search__question" onSubmit={handleSearch}>
        <label htmlFor="rag-question">Ask an English question about the approved documents</label>
        <div>
          <input
            id="rag-question"
            type="text"
            minLength={3}
            maxLength={500}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="For example: How long does standard delivery take?"
          />
          <button className="button" type="submit" disabled={searching || question.trim().length < 3}>
            {searching ? "Checking evidence…" : "Get grounded answer"}
          </button>
        </div>
      </form>

      {error ? <div className="notice notice--error" role="alert">{error}</div> : null}
      {result ? (
        <EvidenceResult
          result={result}
          onRetry={() => void requestGroundedAnswer()}
          retrying={searching}
        />
      ) : null}
    </section>
  );
}

function EvidenceResult({
  result,
  onRetry,
  retrying,
}: {
  result: RagAnswerResponse;
  onRetry: () => void;
  retrying: boolean;
}) {
  if (result.status === "unavailable") {
    const providerUnavailable =
      result.reason_codes.includes("answer_provider_unavailable") && result.evidence.length > 0;
    return (
      <div className="evidence-search__empty" role="status">
        <h3>Grounded answer is temporarily unavailable</h3>
        {providerUnavailable ? (
          <>
            <p>
              Relevant evidence was found, but Gemini is temporarily unavailable. No answer was generated.
            </p>
            <button className="button button--secondary" type="button" disabled={retrying} onClick={onRetry}>
              {retrying ? "Retrying…" : "Retry grounded answer"}
            </button>
          </>
        ) : (
          <p>No AI claim was returned. Your dashboard and Phase 1 evidence index are unaffected.</p>
        )}
        <TechnicalSummary result={result} />
      </div>
    );
  }
  if (result.status === "insufficient_evidence") {
    return (
      <div className="evidence-search__empty" role="status">
        <h3>Insufficient evidence</h3>
        <p>No source excerpt passed the relevance check, so the system returned no evidence instead of guessing.</p>
        <TechnicalSummary result={result} />
      </div>
    );
  }
  return (
    <div className="evidence-search__results" aria-live="polite">
      <h3>Grounded answer</h3>
      <p>Each claim was checked against an exact quote from retrieved evidence.</p>
      <ol>
        {result.claims.map((claim, index) => (
          <li key={`${claim.chunk_id}-${index}`} className="evidence-search__item">
            <p>{claim.text}</p>
            <strong>{claim.citation}</strong>
            <blockquote>{claim.supporting_quote}</blockquote>
          </li>
        ))}
      </ol>
      <details>
        <summary>Technical retrieval evidence</summary>
        <ol>
          {result.evidence.map((item) => (
            <li key={item.chunk_id} className="evidence-search__item">
              <div>
                <strong>{item.citation}</strong>
                <span>{item.document_type.replaceAll("_", " ")} · version {item.document_version}</span>
              </div>
              <blockquote>{item.excerpt}</blockquote>
              <dl>
                <div><dt>Rank</dt><dd>{item.rank}</dd></div>
                <div><dt>Retrieval score</dt><dd>{item.technical.retrieval_score.toFixed(4)}</dd></div>
                <div><dt>Chunk ID</dt><dd><code>{item.chunk_id.slice(0, 16)}…</code></dd></div>
              </dl>
            </li>
          ))}
        </ol>
      </details>
      <TechnicalSummary result={result} />
    </div>
  );
}

function TechnicalSummary({ result }: { result: RagAnswerResponse }) {
  return (
    <details className="evidence-search__technical">
      <summary>Search details</summary>
      <p>
        {result.technical.selected_method} searched {result.technical.searched_document_count} documents and {result.technical.searched_chunk_count} chunks. Total answer time: {result.latency_ms.toFixed(1)} ms.
      </p>
      {result.reason_codes.length > 0 ? <p>Reason: {result.reason_codes.join(", ")}</p> : null}
    </details>
  );
}

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : "The evidence request could not be completed.";
}
