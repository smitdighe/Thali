import type { FaultState, HealthResponse, MetricsResponse, ProviderReport, RecommendResponse, RefineRequest, StreamParsed } from "./types";

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

export function refine(body: RefineRequest, signal: AbortSignal): Promise<RecommendResponse> {
  return request<RecommendResponse>("/api/v1/refine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export interface StreamHandlers {
  onParsed: (value: StreamParsed) => void;
  onProvider: (report: ProviderReport) => void;
}

interface Frame {
  event: string;
  data: string;
}

function parseFrame(raw: string): Frame | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}

function dispatch(frame: Frame, handlers: StreamHandlers): RecommendResponse | null {
  let payload: unknown;
  try {
    payload = JSON.parse(frame.data);
  } catch {
    throw new Error("Malformed stream frame");
  }
  if (frame.event === "parsed") handlers.onParsed(payload as StreamParsed);
  else if (frame.event === "provider") handlers.onProvider(payload as ProviderReport);
  else if (frame.event === "done") return payload as RecommendResponse;
  else if (frame.event === "error") throw new Error("Stream reported an error");
  return null;
}

async function readStream(query: string, signal: AbortSignal, handlers: StreamHandlers): Promise<RecommendResponse> {
  const res = await fetch("/api/v1/recommend/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ query }),
    signal,
  });
  if (!res.ok || res.body === null) throw new Error(`Stream unavailable (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = parseFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (frame) {
        const done = dispatch(frame, handlers);
        if (done) return done;
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
  throw new Error("Stream ended before the result");
}

export async function recommendStream(
  query: string,
  signal: AbortSignal,
  handlers: StreamHandlers,
): Promise<RecommendResponse> {
  try {
    return await readStream(query, signal, handlers);
  } catch (error) {
    if (signal.aborted) throw error;
    return recommend(query, signal);
  }
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/v1/health");
}

export function getMetrics(signal: AbortSignal): Promise<MetricsResponse> {
  return request<MetricsResponse>("/api/v1/metrics", { signal });
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
