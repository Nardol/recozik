const API_BASE =
  process.env.NEXT_PUBLIC_RECOZIK_API_BASE?.replace(/\/$/, "") ?? "/api";

function resolveWsOrigin(): URL {
  if (typeof window === "undefined") {
    throw new Error("WebSocket connections require a browser environment");
  }
  if (API_BASE.startsWith("http")) {
    return new URL(API_BASE);
  }
  return new URL(window.location.origin + API_BASE);
}

function buildJobPath(jobId: string): string {
  const suffix = `/ws/jobs/${jobId}`;
  const basePath = resolveWsOrigin().pathname.replace(/\/$/, "");
  const combined = `${basePath}${suffix}`.replace(/\/+/g, "/");
  return combined.startsWith("/") ? combined : `/${combined}`;
}

export function createJobWebSocket(jobId: string): WebSocket {
  const origin = resolveWsOrigin();
  const protocol = origin.protocol === "https:" ? "wss:" : "ws:";
  const path = buildJobPath(jobId);
  const url = `${protocol}//${origin.host}${path}`;
  return new WebSocket(url);
}
