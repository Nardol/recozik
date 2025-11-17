"use client";

import { FormEvent, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import { useToken } from "./TokenProvider";

export function TokenForm() {
  const { setToken, status } = useToken();
  const { t } = useI18n();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      if (!value.trim()) {
        setError(t("tokenForm.errorRequired"));
        return;
      }
      setToken(value.trim());
      setValue("");
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("tokenForm.errorGeneric"),
      );
    }
  };

  return (
    <section aria-labelledby="token-form-title" className="panel">
      <h2 id="token-form-title">{t("tokenForm.title")}</h2>
      <p className="muted">{t("tokenForm.description")}</p>
      <form onSubmit={handleSubmit} className="stack">
        <label htmlFor="token-input">{t("tokenForm.label")}</label>
        <input
          id="token-input"
          name="token"
          type="password"
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-describedby="token-help"
          disabled={status === "loading"}
          required
        />
        <p id="token-help" className="muted">
          {t("tokenForm.help")}
        </p>
        <button
          type="submit"
          className="primary"
          disabled={status === "loading"}
        >
          {status === "loading" ? t("tokenForm.saving") : t("tokenForm.save")}
        </button>
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
      </form>
    </section>
  );
}
