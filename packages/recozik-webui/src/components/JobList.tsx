"use client";

import { useEffect, useRef } from "react";
import { JobDetail, fetchJobDetail } from "../lib/api";
import { MessageKey, useI18n } from "../i18n/I18nProvider";
import { useToken } from "./TokenProvider";
import { createJobWebSocket } from "../lib/job-websocket";

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

const COMPLETED_STATUSES = new Set(["completed", "failed"]);

export function JobList({ jobs, onUpdate, sectionId }: Props) {
  const { token } = useToken();
  const { t } = useI18n();
  const headingId = sectionId ? `${sectionId}-jobs-title` : "jobs-title";
  const socketsRef = useRef<Map<string, WebSocket>>(new Map());

  useEffect(() => {
    const sockets = socketsRef.current;
    return () => {
      sockets.forEach((socket) => socket.close());
      sockets.clear();
    };
  }, []);

  useEffect(() => {
    if (!token) {
      socketsRef.current.forEach((socket) => socket.close());
      socketsRef.current.clear();
      return;
    }
    const inFlight = jobs.filter((job) => !COMPLETED_STATUSES.has(job.status));
    if (inFlight.length === 0) {
      socketsRef.current.forEach((socket) => socket.close());
      socketsRef.current.clear();
      return;
    }

    const known = socketsRef.current;
    const activeIds = new Set(inFlight.map((job) => job.job_id));

    known.forEach((socket, jobId) => {
      if (!activeIds.has(jobId)) {
        socket.close();
        known.delete(jobId);
      }
    });

    inFlight.forEach((job) => {
      if (known.has(job.job_id)) {
        return;
      }
      try {
        const ws = createJobWebSocket(job.job_id);
        ws.addEventListener("message", async (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload?.job) {
              onUpdate(payload.job as JobDetail);
              return;
            }
            if (!token) {
              return;
            }
            const detail = await fetchJobDetail(token, job.job_id);
            onUpdate(detail);
          } catch (error) {
            console.warn("Unable to process job event", job.job_id, error);
          }
        });
        ws.addEventListener("close", () => {
          known.delete(job.job_id);
        });
        ws.addEventListener("error", (error) => {
          console.warn("Job WebSocket error", job.job_id, error);
        });
        known.set(job.job_id, ws);
      } catch (error) {
        console.warn("Unable to open WebSocket for job", job.job_id, error);
      }
    });

    const interval = setInterval(async () => {
      await Promise.all(
        inFlight.map(async (job) => {
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
