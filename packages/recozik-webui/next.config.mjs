const uploadBodyLimit =
  process.env.RECOZIK_WEBUI_UPLOAD_LIMIT?.trim() || "100mb";

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: {
      bodySizeLimit: uploadBodyLimit,
    },
    proxyClientMaxBodySize: uploadBodyLimit,
  },
};

export default nextConfig;
