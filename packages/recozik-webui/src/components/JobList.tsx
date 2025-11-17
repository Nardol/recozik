"use client";

import { useEffect } from "react";
import { JobDetail, fetchJobDetail } from "../lib/api";
import { MessageKey, useI18n } from "../i18n/I18nProvider";
import { useToken } from "./TokenProvider";

interface Props {
  jobs: JobDetail[];
  onUpdate: (job: JobDetail) => void;
  sectionId?: string;
}

const STATUS_KEYS: Record<string, MessageKey> = {
  queued: "jobs.status.queued",
  running: "jobs.status.running",
  completed: "jobs.status.completed",
  failed: "jobs.status.failed",
};

export function JobList({ jobs, onUpdate, sectionId }: Props) {
  const { token } = useToken();
  const { t } = useI18n();
  const headingId = sectionId ? `${sectionId}-jobs-title` : "jobs-title";

  useEffect(() => {
    if (!token) return;
    const incomplete = jobs.filter(
      (job) => job.status !== "completed" && job.status !== "failed",
    );
    if (incomplete.length === 0) return;

    const interval = setInterval(async () => {
      await Promise.all(
        incomplete.map(async (job) => {
          try {
            const detail = await fetchJobDetail(token, job.job_id);
            onUpdate(detail);
          } catch (error) {
            console.warn("Unable to refresh job", job.job_id, error);
          }
        }),
      );
    }, 4000);

    return () => clearInterval(interval);
  }, [jobs, token, onUpdate]);

  const statusLabel = (status: string) => {
    const key = STATUS_KEYS[status];
    return key ? t(key) : status;
  };

  if (jobs.length === 0) {
    return (
      <section id={sectionId} aria-labelledby={headingId} className="panel">
        <h2 id={headingId}>{t("jobs.title")}</h2>
        <p>{t("jobs.empty")}</p>
      </section>
    );
  }

  return (
    <section id={sectionId} aria-labelledby={headingId} className="panel">
      <h2 id={headingId}>{t("jobs.title")}</h2>
      <div className="table-wrapper" role="region" aria-live="polite">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("jobs.th.id")}</th>
              <th scope="col">{t("jobs.th.status")}</th>
              <th scope="col">{t("jobs.th.updated")}</th>
              <th scope="col">{t("jobs.th.messages")}</th>
              <th scope="col">{t("jobs.th.result")}</th>
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
                    {statusLabel(job.status)}
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
                      <summary>{t("jobs.viewJson")}</summary>
                      <pre>{JSON.stringify(job.result, null, 2)}</pre>
                    </details>
                  ) : (
                    <span className="muted">{t("jobs.pending")}</span>
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
