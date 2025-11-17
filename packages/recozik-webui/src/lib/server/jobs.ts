import "server-only";

import type { JobDetail } from "../api";
import { serverFetch, serverFormPost } from "./api";

type UploadJobResponse = {
  job_id: string;
};

export async function serverCreateJob(
  token: string,
  payload: FormData,
): Promise<JobDetail> {
  const response = await serverFormPost<UploadJobResponse>(
    "/identify/upload",
    token,
    payload,
  );
  return serverFetch(`/jobs/${response.job_id}`, token, { method: "GET" });
}
