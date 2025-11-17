"use client";

import { useEffect } from "react";
import { JobDetail, fetchJobDetail } from "../lib/api";
import { useToken } from "./TokenProvider";

interface Props {
  jobs: JobDetail[];
  onUpdate: (job: JobDetail) => void;
  sectionId?: string;
}

export function JobList({ jobs, onUpdate, sectionId }: Props) {
  const { token } = useToken();

  useEffect(() => {
    if (!token) return;
    const incomplete = jobs.filter(
      (job) => job.status !== "completed" && job.status !== "failed",
    );
    if (incomplete.length === 0) return;

    const interval = setInterval(async () => {
      for (const job of incomplete) {
        try {
          const detail = await fetchJobDetail(token, job.job_id);
          onUpdate(detail);
        } catch (error) {
          console.warn("Unable to refresh job", job.job_id, error);
        }
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [jobs, token, onUpdate]);

  if (jobs.length === 0) {
    return (
      <section id={sectionId} aria-labelledby="jobs-title" className="panel">
        <h2 id="jobs-title">Jobs</h2>
        <p>No identify jobs yet. Submit an upload to see live results.</p>
      </section>
    );
  }

  return (
    <section id={sectionId} aria-labelledby="jobs-title" className="panel">
      <h2 id="jobs-title">Jobs</h2>
      <div className="table-wrapper" role="region" aria-live="polite">
        <table>
          <thead>
            <tr>
              <th scope="col">Job ID</th>
              <th scope="col">Status</th>
              <th scope="col">Updated</th>
              <th scope="col">Messages</th>
              <th scope="col">Result summary</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id}>
                <td>
                  <code>{job.job_id}</code>
                </td>
                <td>
                  <span className={`badge badge-${job.status.toLowerCase()}`}>
                    {job.status}
                  </span>
                  {job.error ? <p className="error">{job.error}</p> : null}
                </td>
                <td>{new Date(job.updated_at).toLocaleString()}</td>
                <td>
                  <ul>
                    {job.messages.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                </td>
                <td>
                  {job.result ? (
                    <details>
                      <summary>View JSON</summary>
                      <pre>{JSON.stringify(job.result, null, 2)}</pre>
                    </details>
                  ) : (
                    <span className="muted">Pending</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
