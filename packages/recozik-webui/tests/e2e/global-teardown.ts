import type { ChildProcess } from "node:child_process";

declare global {
  var __MOCK_SERVER__: ChildProcess | null | undefined;
}

export default async function globalTeardown() {
  const mock = global.__MOCK_SERVER__;
  if (mock && !mock.killed) {
    try {
      mock.kill("SIGTERM");
      await new Promise((resolve) => setTimeout(resolve, 500));
    } catch {
      /* ignore */
    }
  }
}
