import "server-only";

import type { JobDetail } from "../api";
import { serverFetch, serverFormPost } from "./api";

export async function serverCreateJob(
  token: string,
  payload: FormData,
): Promise<JobDetail> {
  const response = await serverFormPost("/identify/upload", token, payload);
  const jobId = response.job_id as string;
  return serverFetch(`/jobs/${jobId}`, token, { method: "GET" });
}
