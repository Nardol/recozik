import "server-only";

import type { JobDetail } from "../api";
import { serverFetch, serverFormPost } from "./api";

type UploadJobResponse = {
  job_id: string;
};

export async function serverCreateJob(payload: FormData): Promise<JobDetail> {
  const response = await serverFormPost<UploadJobResponse>(
    "/identify/upload",
    payload,
  );
  return serverFetch(`/jobs/${response.job_id}`, { method: "GET" });
}
