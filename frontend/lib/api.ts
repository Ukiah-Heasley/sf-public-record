import type {
  DashboardResponse,
  HearingDetail,
  HearingSummary,
  SearchRequest,
  SearchResponse
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_PLANLENS_API_BASE_URL ?? "http://127.0.0.1:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    throw new Error(`API ${response.status}: ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function getDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>("/dashboard");
}

export function listHearings(): Promise<HearingSummary[]> {
  return apiFetch<HearingSummary[]>("/hearings");
}

export function getHearing(hearingId: string): Promise<HearingDetail> {
  return apiFetch<HearingDetail>(`/hearings/${encodeURIComponent(hearingId)}`);
}

export function searchEvidence(request: SearchRequest): Promise<SearchResponse> {
  return apiFetch<SearchResponse>("/search", {
    method: "POST",
    body: JSON.stringify(request)
  });
}
