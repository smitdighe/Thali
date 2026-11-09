import type { FaultState, HealthResponse, RecommendResponse } from "./types";

export class ApiError extends Error {
  status: number;
  requestId: string | null;

  constructor(status: number, message: string, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function messageFromBody(body: unknown, fallback: string): string {
  if (!isRecord(body)) return fallback;
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first: unknown = detail[0];
    if (isRecord(first) && typeof first.msg === "string") return first.msg;
  }
  if (typeof body.error === "string") return body.error;
  return fallback;
}

function requestIdFrom(res: Response, body: unknown): string | null {
  const header = res.headers.get("X-Request-ID");
  if (header) return header;
  if (isRecord(body) && typeof body.request_id === "string") return body.request_id;
  return null;
}

async function readBody(res: Response): Promise<unknown> {
  try {
    const parsed: unknown = await res.json();
    return parsed;
  } catch {
    return null;
  }
}

function failure(res: Response, body: unknown): ApiError {
  return new ApiError(res.status, messageFromBody(body, `Request failed (${res.status})`), requestIdFrom(res, body));
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const body = await readBody(res);
  if (!res.ok) throw failure(res, body);
  return body as T;
}

export function recommend(query: string, signal: AbortSignal): Promise<RecommendResponse> {
  return request<RecommendResponse>("/api/v1/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
    signal,
  });
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/v1/health");
}

export async function getFaults(): Promise<FaultState | null> {
  const res = await fetch("/mock/_faults");
  if (res.status === 404) return null;
  const body = await readBody(res);
  if (!res.ok) throw failure(res, body);
  return body as FaultState;
}

export function setFaults(patch: Partial<FaultState>): Promise<FaultState> {
  return request<FaultState>("/mock/_faults", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export function resetFaults(): Promise<FaultState> {
  return request<FaultState>("/mock/_faults/reset", { method: "POST" });
}
