const http = require("http");

const PORT = process.env.MOCK_API_PORT || 9999;

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

const sendJson = (res, status, data) => {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.end(JSON.stringify(data));
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (url.pathname === "/whoami") {
    return sendJson(res, 200, whoamiResponse);
  }
  if (url.pathname.startsWith("/jobs")) {
    return sendJson(res, 200, jobsResponse);
  }
  if (url.pathname === "/health") {
    return sendJson(res, 200, { ok: true });
  }
  res.statusCode = 404;
  res.end("not found");
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Mock API listening on ${PORT}`);
});

process.on("SIGTERM", () => server.close(() => process.exit(0)));
process.on("SIGINT", () => server.close(() => process.exit(0)));
