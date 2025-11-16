const API_BASE =
  process.env.NEXT_PUBLIC_RECOZIK_API_BASE?.replace(/\/$/, "") ??
  "http://localhost:8000";

async function apiFetch<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers as HeadersInit | undefined);
  headers.set("X-API-Token", token);
  if (!(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

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

export interface JobDetail {
  job_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
  messages: string[];
  result: Record<string, unknown> | null;
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

export async function fetchWhoami(token: string): Promise<WhoAmI> {
  return apiFetch("/whoami", token, { cache: "no-store" });
}

export async function uploadJob(token: string, formData: FormData) {
  return apiFetch<{ job_id: string }>("/identify/upload", token, {
    method: "POST",
    body: formData,
  });
}

export async function fetchJobDetail(
  token: string,
  jobId: string,
): Promise<JobDetail> {
  return apiFetch(`/jobs/${jobId}`, token, { cache: "no-store" });
}

export async function fetchAdminTokens(
  token: string,
): Promise<TokenResponse[]> {
  return apiFetch("/admin/tokens", token, { cache: "no-store" });
}

export async function createToken(
  token: string,
  payload: TokenCreatePayload,
): Promise<TokenResponse> {
  return apiFetch("/admin/tokens", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getApiBase() {
  return API_BASE;
}
