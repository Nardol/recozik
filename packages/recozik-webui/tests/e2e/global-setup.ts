import { spawn, type ChildProcess } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

declare global {
  var __MOCK_SERVER__: ChildProcess | null | undefined;
}

const DEFAULT_PORT = process.env.MOCK_API_PORT || "10099";
const MOCK_BASE = (port: string) => `http://localhost:${port}`;

async function waitForHealth(port: string, retries = 90, intervalMs = 250) {
  const base = MOCK_BASE(port);
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(`${base}/health`);
      if (res.ok) return true;
    } catch {
      // keep trying
    }
    await delay(intervalMs);
  }
  return false;
}

export default async function globalSetup() {
  const port = DEFAULT_PORT;
  const base = MOCK_BASE(port);

  // Check if a mock is already running
  let alreadyRunning = false;
  try {
    const res = await fetch(`${base}/health`);
    alreadyRunning = res.ok;
  } catch {
    alreadyRunning = false;
  }

  if (alreadyRunning) {
    global.__MOCK_SERVER__ = null;
    return;
  }

  const mock = spawn("node", ["tests/e2e/mock-api-server.js"], {
    cwd: process.cwd(),
    env: { ...process.env, MOCK_API_PORT: port },
    stdio: ["ignore", "pipe", "pipe"],
    detached: false,
  });
  mock.stderr?.on("data", (chunk) => {
    console.error("[mock-api]", chunk.toString());
  });
  const ready = await waitForHealth(port);
  if (!ready) {
    mock.kill("SIGTERM");
    throw new Error(`Mock API did not become ready on port ${port}`);
  }
  global.__MOCK_SERVER__ = mock;
}
