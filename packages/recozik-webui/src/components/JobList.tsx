"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
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
      <h2 id={headingId} data-testid="jobs-title">
        {t("jobs.title")}
      </h2>
      <div
        className="table-wrapper"
        role="region"
        aria-live="polite"
        data-testid="jobs-table-wrapper"
      >
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
              <tr key={job.job_id} data-testid={`job-row-${job.job_id}`}>
                <td>
                  <code data-testid="job-id">{job.job_id}</code>
                </td>
                <td>
                  <span
                    className={`badge badge-${job.status.toLowerCase()}`}
                    data-testid="job-status"
                  >
                    {statusLabel(job.status)}
                  </span>
                  {job.error ? <p className="error">{job.error}</p> : null}
                </td>
                <td>{new Date(job.updated_at).toLocaleString()}</td>
                <td>
                  <ul data-testid="job-messages">
                    {job.messages.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                </td>
                <td>
                  <ResultSummary job={job} t={t} />
                  {job.result ? (
                    <details>
                      <summary>{t("jobs.viewJson")}</summary>
                      <pre>{JSON.stringify(job.result, null, 2)}</pre>
                    </details>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

interface ResultSummaryProps {
  job: JobDetail;
  t: (key: MessageKey, values?: Record<string, string | number>) => string;
}

function ResultSummary({ job, t }: ResultSummaryProps) {
  if (job.error) {
    return (
      <p className="error">{t("jobs.summary.error", { message: job.error })}</p>
    );
  }

  if (job.status !== "completed") {
    const statusKey = `jobs.status.${job.status}` as MessageKey;
    return <span className="muted">{t(statusKey)}</span>;
  }

  if (!job.result) {
    return <span className="muted">{t("jobs.summary.noResult")}</span>;
  }

  const match = job.result.matches?.[0];
  const metadataLine = formatMetadata(job.result.metadata);
  const note = job.result.audd_note;
  const auddError = job.result.audd_error;
  const sourceLine = job.result.match_source
    ? t("jobs.summary.source", { source: job.result.match_source })
    : null;

  const lines: ReactNode[] = [];

  if (match) {
    const artist = match.artist || t("jobs.summary.unknownArtist");
    const title = match.title || t("jobs.summary.unknownTitle");
    const release =
      match.release_group_title || match.releases?.[0]?.title || undefined;
    const score = formatScore(match.score);

    lines.push(
      <p key="headline">
        <strong>{artist ? `${artist} — ${title}` : title}</strong>
      </p>,
    );

    if (release) {
      lines.push(
        <p key="release" className="muted">
          {release}
        </p>,
      );
    }

    const facts: string[] = [];
    if (score !== null) {
      facts.push(t("jobs.summary.score", { score }));
    }
    if (sourceLine) {
      facts.push(sourceLine);
    }
    if (facts.length) {
      lines.push(
        <p key="facts" className="muted">
          {facts.join(" · ")}
        </p>,
      );
    }
  } else {
    lines.push(
      <p key="no-match" className="muted">
        {t("jobs.summary.noMatches")}
      </p>,
    );
    if (sourceLine) {
      lines.push(
        <p key="source" className="muted">
          {sourceLine}
        </p>,
      );
    }
  }

  if (metadataLine) {
    lines.push(
      <p key="metadata" className="muted">
        {t("jobs.summary.metadata", { metadata: metadataLine })}
      </p>,
    );
  }

  if (note) {
    lines.push(
      <p key="note" className="muted">
        {t("jobs.summary.note", { note })}
      </p>,
    );
  }

  if (auddError) {
    lines.push(
      <p key="audd-error" className="error">
        {t("jobs.summary.auddError", { message: auddError })}
      </p>,
    );
  }

  return <div className="result-summary">{lines}</div>;
}

function formatScore(value: number | undefined): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null;
  }
  const scaled = value <= 1 ? value * 100 : value;
  return Math.round(Math.min(Math.max(scaled, 0), 100));
}

function formatMetadata(
  metadata: Record<string, string> | null,
): string | null {
  if (!metadata) {
    return null;
  }
  const preferred = ["title", "artist", "album", "track", "composer"];
  const values: string[] = [];
  const seen = new Set<string>();

  for (const key of preferred) {
    const value = metadata[key];
    if (value && !seen.has(value)) {
      values.push(value);
      seen.add(value);
    }
  }

  Object.values(metadata).forEach((value) => {
    if (value && !seen.has(value)) {
      values.push(value);
      seen.add(value);
    }
  });

  if (values.length === 0) {
    return null;
  }
  return values.slice(0, 3).join(" · ");
}
