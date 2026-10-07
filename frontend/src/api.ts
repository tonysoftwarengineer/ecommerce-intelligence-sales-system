import type {
  CsvPreviewResponse,
  DataValidationResponse,
  DistinctValuesResponse,
  GenericAnalysisResponse,
  MappingSuggestionsResponse,
  ProductDemandRequest,
  ProductDemandResponse,
  RevenueMode,
  SalesConfiguration,
  SchemaMappingResponse,
} from "./types";

// Guest uploads belong to an HTTP-only, host-scoped session cookie. In local
// development, keep the API hostname aligned with the address the user opened
// in the browser: 127.0.0.1 -> 127.0.0.1 and localhost -> localhost.
// Deployments and automated tests still provide VITE_API_URL explicitly.
const BASE_URL =
  import.meta.env.VITE_API_URL ?? `${window.location.protocol}//${window.location.hostname}:8000`;

interface ApiErrorBody {
  detail?: string | { message?: string; errors?: string[] };
}

function errorMessage(path: string, status: number, body: ApiErrorBody | null): string {
  if (typeof body?.detail === "string") return body.detail;
  if (body?.detail?.message) {
    const errors = body.detail.errors?.join(" ");
    return errors ? `${body.detail.message}: ${errors}` : body.detail.message;
  }
  return `Request to ${path} failed (${status})`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new Error(errorMessage(path, response.status, body));
  }
  return response.json();
}

function postJson<T>(path: string, body: object): Promise<T> {
  return fetchJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function uploadCsv(file: File): Promise<CsvPreviewResponse> {
  const form = new FormData();
  form.append("file", file);
  return fetchJson<CsvPreviewResponse>("/api/v1/uploads/preview", {
    method: "POST",
    body: form,
  });
}

export function validateMapping(
  uploadId: string,
  mapping: Record<string, string>,
  revenueMode: RevenueMode,
): Promise<SchemaMappingResponse> {
  return postJson<SchemaMappingResponse>("/api/v1/uploads/validate-mapping", {
    upload_id: uploadId,
    mapping,
    revenue_mode: revenueMode,
  });
}

export function fetchDistinctValues(
  uploadId: string,
  columns: string[],
): Promise<DistinctValuesResponse> {
  return postJson<DistinctValuesResponse>("/api/v1/uploads/distinct-values", {
    upload_id: uploadId,
    columns,
  });
}

export function fetchMappingSuggestions(
  uploadId: string,
  revenueMode: RevenueMode,
): Promise<MappingSuggestionsResponse> {
  return postJson<MappingSuggestionsResponse>("/api/v1/uploads/mapping-suggestions", {
    upload_id: uploadId,
    revenue_mode: revenueMode,
  });
}

export function validateData(config: SalesConfiguration): Promise<DataValidationResponse> {
  return postJson<DataValidationResponse>("/api/v1/uploads/validate-data", config);
}

export function analyzeUpload(
  config: SalesConfiguration,
  confirmQuarantine: boolean,
  latestPeriodComplete: boolean,
): Promise<GenericAnalysisResponse> {
  return postJson<GenericAnalysisResponse>("/api/v1/uploads/analyze", {
    ...config,
    confirm_quarantine: confirmQuarantine,
    latest_period_complete: latestPeriodComplete,
  });
}

export function fetchAnalysis(
  analysisId: string,
  currency?: string,
): Promise<GenericAnalysisResponse> {
  const query = currency ? `?currency=${encodeURIComponent(currency)}` : "";
  return fetchJson<GenericAnalysisResponse>(`/api/v1/analyses/${analysisId}${query}`);
}

export function analyzeProductDemand(
  analysisId: string,
  request: ProductDemandRequest,
): Promise<ProductDemandResponse> {
  return postJson<ProductDemandResponse>(
    `/api/v1/analyses/${analysisId}/product-demand`,
    request,
  );
}

export function deleteUpload(uploadId: string): Promise<void> {
  return fetch(`${BASE_URL}/api/v1/uploads/${uploadId}`, {
    method: "DELETE",
    credentials: "include",
  }).then(
    (response) => {
      if (!response.ok && response.status !== 404) {
        throw new Error(`Could not remove temporary upload (${response.status})`);
      }
    },
  );
}

export function deleteAnalysis(analysisId: string): Promise<void> {
  return fetch(`${BASE_URL}/api/v1/analyses/${analysisId}`, {
    method: "DELETE",
    credentials: "include",
  }).then(
    (response) => {
      if (!response.ok && response.status !== 404) {
        throw new Error(`Could not remove analysis session (${response.status})`);
      }
    },
  );
}

export function downloadUrl(path: string): string {
  return `${BASE_URL}${path}`;
}
