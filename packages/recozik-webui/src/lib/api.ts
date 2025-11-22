const RAW_API_BASE =
  process.env.NEXT_PUBLIC_RECOZIK_API_BASE?.replace(/\/$/, "") ?? "/api";
function resolveApiBase(): string {
  if (RAW_API_BASE.startsWith("http")) {
    return RAW_API_BASE;
  }
  if (typeof window === "undefined") {
    const origin =
      process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ??
      "http://localhost:3000";
    return `${origin}${RAW_API_BASE}`;
  }
  const origin =
    typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
      : "http://localhost:3000";
  return `${origin}${RAW_API_BASE}`;
}
const API_BASE = resolveApiBase();
const DEFAULT_TIMEOUT_MS = 30_000;

type ApiRequestInit = RequestInit & { timeoutMs?: number };

async function apiFetch<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const headers = new Headers(init?.headers as HeadersInit | undefined);
  if (!(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const { timeoutMs, ...requestInit } = init ?? {};
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...requestInit,
      headers,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(detail || response.statusText);
  }
  if (response.status === 204) {
    return {} as T;
  }
  return (await response.json()) as T;
}

export interface WhoAmI {
  user_id: string;
  display_name: string | null;
  roles: string[];
  allowed_features: string[];
}

export interface ReleaseSummary {
  title?: string | null;
  release_id?: string | null;
  date?: string | null;
  country?: string | null;
}

export interface MatchSummary {
  score: number;
  recording_id?: string | null;
  title?: string | null;
  artist?: string | null;
  release_group_id?: string | null;
  release_group_title?: string | null;
  releases?: ReleaseSummary[] | null;
}

export interface IdentifyResult {
  matches: MatchSummary[];
  match_source: string | null;
  metadata: Record<string, string> | null;
  audd_note: string | null;
  audd_error: string | null;
  fingerprint: string;
  duration_seconds: number;
}

export interface JobDetail {
  job_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
  messages: string[];
  result: IdentifyResult | null;
  error: string | null;
}

export interface TokenResponse {
  token: string;
  user_id: string;
  display_name: string;
  roles: string[];
  allowed_features: string[];
  quota_limits: Record<string, number | null>;
}

export interface TokenCreatePayload {
  token?: string;
  user_id: string;
  display_name: string;
  roles: string[];
  allowed_features: string[];
  quota_limits: Record<string, number | null>;
}

export async function fetchWhoami(): Promise<WhoAmI> {
  return apiFetch("/whoami", { cache: "no-store", credentials: "include" });
}

export async function uploadJob(formData: FormData) {
  return apiFetch<{ job_id: string }>("/identify/upload", {
    method: "POST",
    body: formData,
    credentials: "include",
    timeoutMs: 120_000,
  });
}

export async function fetchJobDetail(jobId: string): Promise<JobDetail> {
  return apiFetch(`/jobs/${jobId}`, {
    cache: "no-store",
    credentials: "include",
  });
}

interface JobsQuery {
  limit?: number;
  offset?: number;
  userId?: string;
}

export async function fetchJobs(query?: JobsQuery): Promise<JobDetail[]> {
  const params = new URLSearchParams();
  if (query?.limit) {
    params.set("limit", String(query.limit));
  }
  if (typeof query?.offset === "number") {
    params.set("offset", String(query.offset));
  }
  if (query?.userId) {
    params.set("user_id", query.userId);
  }
  const search = params.toString() ? `?${params.toString()}` : "";
  return apiFetch(`/jobs${search}`, {
    cache: "no-store",
    credentials: "include",
  });
}

export async function fetchAdminTokens(): Promise<TokenResponse[]> {
  return apiFetch("/admin/tokens", {
    cache: "no-store",
    credentials: "include",
  });
}

export async function createToken(
  payload: TokenCreatePayload,
): Promise<TokenResponse> {
  return apiFetch("/admin/tokens", {
    method: "POST",
    body: JSON.stringify(payload),
    credentials: "include",
  });
}

export function getApiBase() {
  return API_BASE;
}
