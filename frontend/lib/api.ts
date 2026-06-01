/**
 * api.ts
 * Thin, fully-typed client for the FastAPI backend. All calls go through the
 * Next.js rewrite proxy (`/api/*` -> backend) so the browser stays same-origin.
 */

import type {
  PaginatedSignals,
  ScanResult,
  Signal,
  SignalQuery,
  StatsSummary,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      "Cannot reach the backend. Is the FastAPI server running on :8000?",
      0
    );
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new ApiError(detail, res.status);
  }

  return (await res.json()) as T;
}

function toQuery(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  getStats: () => request<StatsSummary>("/api/stats"),

  listSignals: (q: SignalQuery = {}) =>
    request<PaginatedSignals>(`/api/signals${toQuery(q as Record<string, unknown>)}`),

  getSignal: (id: number) => request<Signal>(`/api/signals/${id}`),

  scan: (background = false) =>
    request<ScanResult>(`/api/signals/scan${toQuery({ background })}`, {
      method: "POST",
    }),
};
