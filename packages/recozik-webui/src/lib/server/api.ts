import "server-only";
import { cookies } from "next/headers";

const DEFAULT_INTERNAL_BASE = stripTrailingSlash(
  process.env.RECOZIK_INTERNAL_API_BASE || "http://backend:8000",
);

function stripTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function resolveApiBase(): string {
  const preferred = process.env.RECOZIK_WEB_API_BASE?.trim();
  if (preferred && /^https?:\/\//i.test(preferred)) {
    return stripTrailingSlash(preferred);
  }
  return DEFAULT_INTERNAL_BASE;
}

const API_BASE = resolveApiBase();

function resolve(path: string): string {
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new ApiError(detail || response.statusText, response.status);
  }
  return (await response.json()) as T;
}

function buildCookieHeader(): string | undefined {
  const store = cookies();
  const all = store.getAll();
  if (all.length === 0) return undefined;
  return all.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ");
}

export async function serverFetch<T = unknown>(
  path: string,
  init?: RequestInit,
) {
  const headers = new Headers(init?.headers);
  const cookieHeader = buildCookieHeader();
  if (cookieHeader) {
    headers.set("cookie", cookieHeader);
  }
  const response = await fetch(resolve(path), {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  return handleResponse<T>(response);
}

export async function serverFormPost<T = unknown>(
  path: string,
  formData: FormData,
) {
  const headers = new Headers();
  const cookieHeader = buildCookieHeader();
  if (cookieHeader) {
    headers.set("cookie", cookieHeader);
  }
  const response = await fetch(resolve(path), {
    method: "POST",
    body: formData,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  return handleResponse<T>(response);
}
