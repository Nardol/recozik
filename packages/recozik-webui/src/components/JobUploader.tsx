"use client";

import { useEffect, useId } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { JobDetail } from "../lib/api";
import { useI18n } from "../i18n/I18nProvider";
import { DEFAULT_UPLOAD_STATE, uploadAction } from "../app/actions";

interface Props {
  onJobUpdate: (job: JobDetail) => void;
  sectionId?: string;
}

function SubmitButton({
  submitting,
  idle,
}: {
  submitting: string;
  idle: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="primary" disabled={pending}>
      {pending ? submitting : idle}
    </button>
  );
}

export function JobUploader({ onJobUpdate, sectionId }: Props) {
  const { t, locale } = useI18n();
  const fieldsetId = useId();
  const [state, formAction] = useFormState(uploadAction, DEFAULT_UPLOAD_STATE);

  useEffect(() => {
    if (state.status === "success" && state.job) {
      onJobUpdate(state.job);
    }
  }, [state, onJobUpdate]);

  let statusText = "";
  if (state.status === "success" && state.code === "queued") {
    statusText = t("uploader.status.queued");
  } else if (state.status === "error") {
    if (state.code === "missing_token") {
      statusText = t("uploader.error.noToken");
    } else if (state.code === "missing_file") {
      statusText = t("uploader.error.noFile");
    } else {
      statusText = state.message ?? t("uploader.error.generic");
    }
  }

  return (
    <section id={sectionId} aria-labelledby="upload-title" className="panel">
      <h2 id="upload-title">{t("uploader.title")}</h2>
      <p className="muted">{t("uploader.description")}</p>
      <form className="stack" action={formAction}>
        <input type="hidden" name="locale" value={locale} />
        <label htmlFor="file-input">{t("uploader.audio")}</label>
        <input
          id="file-input"
          name="file"
          type="file"
          accept="audio/*"
          required
        />

        <fieldset id={fieldsetId} aria-describedby="options-help">
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
        <SubmitButton
          submitting={t("uploader.submitting")}
          idle={t("uploader.submit")}
        />
      </form>
      <div aria-live="polite" aria-atomic="true" className="status">
        {statusText ? (
          <p
            role={state.status === "error" ? "alert" : "status"}
            className={state.status === "error" ? "error" : ""}
          >
            {statusText}
          </p>
        ) : null}
      </div>
    </section>
  );
}
