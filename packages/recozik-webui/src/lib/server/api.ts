import "server-only";

const RAW_BASE =
  process.env.RECOZIK_WEB_API_BASE ||
  process.env.NEXT_PUBLIC_RECOZIK_API_BASE ||
  "http://localhost:8000";

const API_BASE = RAW_BASE.endsWith("/") ? RAW_BASE.slice(0, -1) : RAW_BASE;

function resolve(path: string): string {
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

async function handleResponse(response: Response) {
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(detail || response.statusText);
  }
  return response.json();
}

export async function serverFetch(
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
  return handleResponse(response);
}

export async function serverFormPost(
  path: string,
  token: string,
  formData: FormData,
) {
  const response = await fetch(resolve(path), {
    method: "POST",
    body: formData,
    headers: {
      "X-API-Token": token,
    },
    cache: "no-store",
  });
  return handleResponse(response);
}
