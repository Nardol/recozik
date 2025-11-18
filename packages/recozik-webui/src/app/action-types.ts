import type { JobDetail } from "../lib/api";

export type LoginState = {
  status: "idle" | "error" | "success";
  message: string;
};

export type UploadState = {
  status: "idle" | "error" | "success";
  code?: "queued" | "missing_token" | "missing_file" | "backend";
  message?: string;
  job?: JobDetail | null;
};
