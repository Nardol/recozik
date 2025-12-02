/* eslint-disable @typescript-eslint/no-require-imports */
const http = require("http");

const PORT = process.env.MOCK_API_PORT || 10099;

// Whitelist of allowed origins for CORS
const ALLOWED_ORIGINS = [
  "http://localhost:3000",
  "http://localhost:4000",
  "http://localhost:10099",
  "http://localhost:9999",
];

const whoamiResponse = {
  user_id: "demo",
  display_name: "Demo",
  roles: ["admin"],
  allowed_features: ["identify", "rename"],
};

const jobsResponse = [
  {
    job_id: "job-pending",
    status: "pending",
    created_at: "2024-01-01T12:00:00Z",
    updated_at: "2024-01-01T12:00:00Z",
    finished_at: null,
    messages: ["Queued"],
    error: null,
    result: null,
  },
  {
    job_id: "job-failed",
    status: "failed",
    created_at: "2024-01-01T12:01:00Z",
    updated_at: "2024-01-01T12:02:00Z",
    finished_at: "2024-01-01T12:02:00Z",
    messages: ["Upload received"],
    error: "Network error",
    result: {
      matches: [],
      match_source: null,
      metadata: null,
      audd_note: null,
      audd_error: null,
      fingerprint: "zzz",
      duration_seconds: 0,
    },
  },
];

let users = [
  {
    id: 1,
    username: "admin",
    email: "admin@example.com",
    display_name: "Administrator",
    is_active: true,
    roles: ["admin"],
    allowed_features: ["identify", "rename"],
    quota_limits: {},
    created_at: "2024-01-01T00:00:00Z",
  },
  {
    id: 2,
    username: "demo",
    email: "demo@example.com",
    display_name: "Demo User",
    is_active: true,
    roles: ["readonly"],
    allowed_features: ["identify"],
    quota_limits: { acoustid_lookup: 100 },
    created_at: "2024-01-02T00:00:00Z",
  },
];

let tokens = [
  {
    token: "demo-token",
    user_id: 1,
    display_name: "Demo admin token",
    roles: ["admin"],
    allowed_features: ["identify", "rename"],
    quota_limits: {},
  },
];

let nextUserId = 3;

const sendJson = (req, res, status, data) => {
  const requestOrigin = req.headers.origin;
  const origin = ALLOWED_ORIGINS.includes(requestOrigin)
    ? requestOrigin
    : "http://localhost:3000";
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader(
    "Access-Control-Allow-Headers",
    "Content-Type,X-API-Token,X-CSRF-Token",
  );
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS");
  res.end(JSON.stringify(data));
};

const parseBody = async (req) =>
  new Promise((resolve) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        resolve({});
      }
    });
  });

const stripApiPrefix = (pathname) =>
  pathname.startsWith("/api") ? pathname.slice(4) || "/" : pathname;

const server = http.createServer(async (req, res) => {
  console.log(`[mock-api] ${req.method} ${req.url}`);
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = stripApiPrefix(url.pathname);

  if (req.method === "OPTIONS") {
    const requestOrigin = req.headers.origin;
    const origin = ALLOWED_ORIGINS.includes(requestOrigin)
      ? requestOrigin
      : "http://localhost:3000";
    res.statusCode = 204;
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Credentials", "true");
    res.setHeader(
      "Access-Control-Allow-Headers",
      "Content-Type,X-API-Token,X-CSRF-Token",
    );
    res.setHeader(
      "Access-Control-Allow-Methods",
      "GET,POST,PUT,DELETE,OPTIONS",
    );
    return res.end();
  }

  if (pathname === "/health") {
    return sendJson(req, res, 200, { ok: true });
  }

  if (pathname === "/whoami") {
    const hasSession =
      req.headers.cookie?.includes("recozik_session=") ?? false;
    if (!hasSession) {
      return sendJson(req, res, 401, { detail: "Unauthorized" });
    }
    return sendJson(req, res, 200, whoamiResponse);
  }

  if (pathname === "/auth/login" && req.method === "POST") {
    // Simulate session cookies
    res.statusCode = 200;
    const cookies = [
      "recozik_session=mock_session; Path=/; HttpOnly; SameSite=Lax",
      "recozik_refresh=mock_refresh; Path=/; HttpOnly; SameSite=Lax",
      "recozik_csrf=mock_csrf; Path=/; SameSite=Lax",
    ];
    res.setHeader("Set-Cookie", cookies);
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify({ status: "ok" }));
  }

  if (pathname === "/auth/logout" && req.method === "POST") {
    res.statusCode = 200;
    res.setHeader("Set-Cookie", [
      "recozik_session=; Path=/; Max-Age=0",
      "recozik_refresh=; Path=/; Max-Age=0",
      "recozik_csrf=; Path=/; Max-Age=0",
    ]);
    res.setHeader("Content-Type", "application/json");
    return res.end(JSON.stringify({ status: "ok" }));
  }

  if (pathname === "/auth/register" && req.method === "POST") {
    const payload = await parseBody(req);
    if (!payload.username || !payload.email || !payload.password) {
      return sendJson(req, res, 400, { detail: "missing_fields" });
    }
    const newUser = {
      id: nextUserId++,
      username: payload.username || `user${nextUserId}`,
      email: payload.email || "user@example.com",
      display_name: payload.display_name ?? null,
      is_active: true,
      roles: payload.roles || ["readonly"],
      allowed_features: payload.allowed_features || [],
      quota_limits: payload.quota_limits || {},
      created_at: new Date().toISOString(),
    };
    users = [...users, newUser];
    // Also create a token to ensure tables grow
    tokens = [
      ...tokens,
      {
        token: `user-${newUser.id}-token`,
        user_id: newUser.id,
        display_name: `Token for ${newUser.username}`,
        roles: newUser.roles,
        allowed_features: newUser.allowed_features,
        quota_limits: newUser.quota_limits,
      },
    ];
    return sendJson(req, res, 200, { status: "ok", user: newUser });
  }

  if (pathname === "/admin/users" && req.method === "GET") {
    return sendJson(req, res, 200, users);
  }

  if (pathname === "/admin/tokens" && req.method === "GET") {
    return sendJson(req, res, 200, tokens);
  }

  if (pathname === "/admin/tokens" && req.method === "POST") {
    const payload = await parseBody(req);
    const created = {
      token: payload.token || `token-${Date.now()}`,
      user_id: payload.user_id ?? 1,
      display_name: payload.display_name || "Generated token",
      roles: payload.roles || ["readonly"],
      allowed_features: payload.allowed_features || [],
      quota_limits: payload.quota_limits || {},
    };
    tokens = [...tokens, created];
    return sendJson(req, res, 200, created);
  }

  const userIdMatch = pathname.match(/^\/admin\/users\/(\d+)(.*)?$/);
  if (userIdMatch) {
    const userId = Number(userIdMatch[1]);
    const tail = userIdMatch[2] || "";
    const user = users.find((u) => u.id === userId);

    if (tail === "/reset-password" && req.method === "POST") {
      return sendJson(req, res, 200, { status: "ok" });
    }

    if (tail === "/sessions" && req.method === "GET") {
      return sendJson(req, res, 200, [
        {
          id: 1,
          user_id: userId,
          created_at: "2024-01-01T00:00:00Z",
          expires_at: "2025-01-01T00:00:00Z",
          refresh_expires_at: "2025-01-08T00:00:00Z",
          remember: true,
        },
      ]);
    }

    if (tail === "/sessions" && req.method === "DELETE") {
      return sendJson(req, res, 200, { status: "ok" });
    }

    if (!user) {
      return sendJson(req, res, 404, { detail: "Not found" });
    }

    if (req.method === "PUT") {
      const payload = await parseBody(req);
      const updated = {
        ...user,
        ...payload,
        email: payload.email ?? user.email,
        display_name:
          payload.display_name === undefined
            ? user.display_name
            : payload.display_name,
        is_active:
          payload.is_active === undefined ? user.is_active : payload.is_active,
        roles: payload.roles ?? user.roles,
        allowed_features: payload.allowed_features ?? user.allowed_features,
        quota_limits: payload.quota_limits ?? user.quota_limits,
      };
      users = users.map((u) => (u.id === userId ? updated : u));
      return sendJson(req, res, 200, updated);
    }

    if (req.method === "DELETE") {
      users = users.filter((u) => u.id !== userId);
      return sendJson(req, res, 200, { status: "ok" });
    }
  }

  if (pathname === "/jobs" && req.method === "GET") {
    return sendJson(req, res, 200, jobsResponse);
  }

  if (pathname.startsWith("/jobs/") && req.method === "GET") {
    const jobId = pathname.split("/")[2];
    const job = jobsResponse.find((j) => j.job_id === jobId);
    if (job) return sendJson(req, res, 200, job);
    return sendJson(req, res, 404, { detail: "Job not found" });
  }

  if (pathname === "/identify/upload" && req.method === "POST") {
    return sendJson(req, res, 200, { job_id: "job-uploaded" });
  }

  // Soft stub for WebSocket probe requests so the UI doesn't throw loudly.
  if (pathname.startsWith("/ws/jobs")) {
    return sendJson(req, res, 200, { status: "ok" });
  }

  res.statusCode = 404;
  res.end("not found");
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Mock API listening on ${PORT}`);
});

process.on("SIGTERM", () => server.close(() => process.exit(0)));
process.on("SIGINT", () => server.close(() => process.exit(0)));
