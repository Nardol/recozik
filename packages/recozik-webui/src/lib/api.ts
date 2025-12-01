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

function getCsrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith("recozik_csrf="));
  return match ? decodeURIComponent(match.split("=", 2)[1]) : undefined;
}

async function apiFetch<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const headers = new Headers(init?.headers as HeadersInit | undefined);
  if (!(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const csrf = getCsrfToken();
  if (csrf) {
    headers.set("X-CSRF-Token", csrf);
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
  user_id: number;
  display_name: string;
  roles: string[];
  allowed_features: string[];
  quota_limits: Record<string, number | null>;
}

export interface TokenCreatePayload {
  token?: string;
  user_id: number;
  display_name: string;
  roles: string[];
  allowed_features: string[];
  quota_limits: Record<string, number | null>;
}

export interface UserResponse {
  id: number;
  username: string;
  email: string; // Required for all users
  display_name: string | null;
  is_active: boolean;
  roles: string[];
  allowed_features: string[];
  quota_limits: Record<string, number | null>;
  created_at: string;
}

export interface RegisterUserPayload {
  username: string;
  email: string;
  display_name?: string | null;
  password: string;
  roles: string[];
  allowed_features: string[];
  quota_limits: Record<string, number | null>;
}

export interface UpdateUserPayload {
  email?: string | null;
  display_name?: string | null;
  is_active?: boolean | null;
  roles: string[];
  allowed_features: string[];
  quota_limits: Record<string, number | null>;
}

export interface ResetPasswordPayload {
  new_password: string;
}

export interface SessionResponse {
  id: number;
  user_id: number;
  created_at: string;
  expires_at: string;
  refresh_expires_at: string;
  remember: boolean;
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

export async function fetchUsers(
  limit?: number,
  offset?: number,
): Promise<UserResponse[]> {
  const params = new URLSearchParams();
  if (limit) {
    params.set("limit", String(limit));
  }
  if (typeof offset === "number") {
    params.set("offset", String(offset));
  }
  const search = params.toString() ? `?${params.toString()}` : "";
  return apiFetch(`/admin/users${search}`, {
    cache: "no-store",
    credentials: "include",
  });
}

export async function fetchUserDetail(userId: number): Promise<UserResponse> {
  return apiFetch(`/admin/users/${userId}`, {
    cache: "no-store",
    credentials: "include",
  });
}

export async function registerUser(
  payload: RegisterUserPayload,
): Promise<{ status: string }> {
  return apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
    credentials: "include",
  });
}

export async function updateUser(
  userId: number,
  payload: UpdateUserPayload,
): Promise<UserResponse> {
  return apiFetch(`/admin/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
    credentials: "include",
  });
}

export async function deleteUser(userId: number): Promise<{ status: string }> {
  return apiFetch(`/admin/users/${userId}`, {
    method: "DELETE",
    credentials: "include",
  });
}

export async function adminResetPassword(
  userId: number,
  payload: ResetPasswordPayload,
): Promise<{ status: string }> {
  return apiFetch(`/admin/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify(payload),
    credentials: "include",
  });
}

export async function fetchUserSessions(
  userId: number,
): Promise<SessionResponse[]> {
  return apiFetch(`/admin/users/${userId}/sessions`, {
    cache: "no-store",
    credentials: "include",
  });
}

export async function revokeUserSessions(
  userId: number,
): Promise<{ status: string }> {
  return apiFetch(`/admin/users/${userId}/sessions`, {
    method: "DELETE",
    credentials: "include",
  });
}

export function getApiBase() {
  return API_BASE;
}
