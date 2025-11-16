"use client";

import { FormEvent, useId, useRef, useState } from "react";
import { JobDetail, uploadJob, fetchJobDetail } from "../lib/api";
import { useToken } from "./TokenProvider";

interface Props {
  onJobUpdate: (job: JobDetail) => void;
}

export function JobUploader({ onJobUpdate }: Props) {
  const { token } = useToken();
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const fieldsetId = useId();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) {
      setError("Please provide a token before uploading files.");
      return;
    }

    const formData = new FormData(event.currentTarget);
    const file = formData.get("file");
    if (!(file instanceof File) || file.size === 0) {
      setError("Select an audio file before submitting.");
      return;
    }

    setBusy(true);
    setError(null);
    setStatusMessage("Uploading…");

    try {
      const { job_id } = await uploadJob(token, formData);
      setStatusMessage("Job queued. Polling for updates…");
      if (formRef.current) {
        formRef.current.reset();
      }
      const detail = await fetchJobDetail(token, job_id);
      onJobUpdate(detail);
    } catch (err) {
      setError((err as Error).message);
      setStatusMessage("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="upload-title" className="panel">
      <h2 id="upload-title">Upload &amp; identify audio</h2>
      <p className="muted">
        Upload an audio clip to trigger the identify workflow. Jobs are
        processed asynchronously with live updates.
      </p>
      <form ref={formRef} className="stack" onSubmit={handleSubmit}>
        <label htmlFor="file-input">Audio file</label>
        <input
          id="file-input"
          name="file"
          type="file"
          accept="audio/*"
          required
          disabled={busy}
        />

        <fieldset
          id={fieldsetId}
          aria-describedby="options-help"
          disabled={busy}
        >
          <legend>Options</legend>
          <label className="option">
            <input type="checkbox" name="metadata_fallback" defaultChecked />{" "}
            Use metadata fallback
          </label>
          <label className="option">
            <input type="checkbox" name="prefer_audd" /> Prefer AudD
          </label>
          <label className="option">
            <input type="checkbox" name="force_audd_enterprise" /> Force AudD
            enterprise mode
          </label>
        </fieldset>
        <p id="options-help" className="muted">
          Advanced flags help control cache usage and AudD behavior. Leave them
          unchecked for default heuristics.
        </p>
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Submitting…" : "Submit job"}
        </button>
      </form>
      <div aria-live="polite" aria-atomic="true" className="status">
        {statusMessage}
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
