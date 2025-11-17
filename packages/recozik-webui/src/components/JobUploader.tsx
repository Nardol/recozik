"use client";

import { FormEvent, useId, useRef, useState } from "react";
import { JobDetail, uploadJob, fetchJobDetail } from "../lib/api";
import { useI18n } from "../i18n/I18nProvider";
import { useToken } from "./TokenProvider";

interface Props {
  onJobUpdate: (job: JobDetail) => void;
  sectionId?: string;
}

export function JobUploader({ onJobUpdate, sectionId }: Props) {
  const { token } = useToken();
  const { t } = useI18n();
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const fieldsetId = useId();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) {
      setError(t("uploader.error.noToken"));
      return;
    }

    const formData = new FormData(event.currentTarget);
    const file = formData.get("file");
    if (!(file instanceof File) || file.size === 0) {
      setError(t("uploader.error.noFile"));
      return;
    }

    setBusy(true);
    setError(null);
    setStatusMessage(t("uploader.status.uploading"));

    try {
      const { job_id } = await uploadJob(token, formData);
      setStatusMessage(t("uploader.status.queued"));
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
    <section id={sectionId} aria-labelledby="upload-title" className="panel">
      <h2 id="upload-title">{t("uploader.title")}</h2>
      <p className="muted">{t("uploader.description")}</p>
      <form ref={formRef} className="stack" onSubmit={handleSubmit}>
        <label htmlFor="file-input">{t("uploader.audio")}</label>
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
          <legend>{t("uploader.options")}</legend>
          <label className="option">
            <input type="checkbox" name="metadata_fallback" defaultChecked />{" "}
            {t("uploader.option.metadata")}
          </label>
          <label className="option">
            <input type="checkbox" name="prefer_audd" />{" "}
            {t("uploader.option.preferAudd")}
          </label>
          <label className="option">
            <input type="checkbox" name="force_audd_enterprise" />{" "}
            {t("uploader.option.forceAudd")}
          </label>
        </fieldset>
        <p id="options-help" className="muted">
          {t("uploader.optionsHelp")}
        </p>
        <button type="submit" className="primary" disabled={busy}>
          {busy ? t("uploader.submitting") : t("uploader.submit")}
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
