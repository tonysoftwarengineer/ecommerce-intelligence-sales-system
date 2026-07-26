import type { ForecastResponse, ReportResponse, SegmentsResponse } from "./types";

const BASE_URL = "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Request to ${path} failed: ${response.status}`);
  }
  return response.json();
}

export function fetchReport(): Promise<ReportResponse> {
  return fetchJson<ReportResponse>("/api/report");
}

export function fetchForecast(): Promise<ForecastResponse> {
  return fetchJson<ForecastResponse>("/api/forecast");
}

export function fetchSegments(): Promise<SegmentsResponse> {
  return fetchJson<SegmentsResponse>("/api/segments");
}
