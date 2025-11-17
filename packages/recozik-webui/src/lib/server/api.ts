import "server-only";

const RAW_BASE =
  process.env.RECOZIK_WEB_API_BASE ||
  process.env.NEXT_PUBLIC_RECOZIK_API_BASE ||
  "http://localhost:8000";

const API_BASE = RAW_BASE.endsWith("/") ? RAW_BASE.slice(0, -1) : RAW_BASE;

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

export async function serverFetch<T = unknown>(
  path: string,
  token: string,
  init?: RequestInit,
) {
  const headers = new Headers(init?.headers);
  headers.set("X-API-Token", token);
  const response = await fetch(resolve(path), {
    ...init,
    headers,
    cache: "no-store",
  });
  return handleResponse<T>(response);
}

export async function serverFormPost<T = unknown>(
  path: string,
  token: string,
  formData: FormData,
) {
  const headers = new Headers();
  headers.set("X-API-Token", token);
  const response = await fetch(resolve(path), {
    method: "POST",
    body: formData,
    headers,
    cache: "no-store",
  });
  return handleResponse<T>(response);
}
