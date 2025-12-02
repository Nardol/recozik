"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "../i18n/I18nProvider";
import { getApiBase } from "../lib/api";
import { useToken } from "./TokenProvider";

interface Props {
  initialError?: string | null;
}

export function LoginForm({ initialError = null }: Props) {
  const { t, locale } = useI18n();
  const { refreshProfile } = useToken();
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const username = (formData.get("username") || "").toString().trim();
    const password = (formData.get("password") || "").toString();
    const remember = formData.get("remember") === "on";
    if (!username || !password) {
      setError(t("login.errorMissing"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const apiBase = getApiBase().replace(/\/$/, "");
      const res = await fetch(`${apiBase}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password, remember }),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(detail || t("login.errorInvalid"));
      }
      await refreshProfile();
      router.replace(`/${locale}`);
      router.refresh();
      form.reset();
    } catch (err) {
      setError((err as Error).message || t("login.errorInvalid"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      className="stack"
      onSubmit={handleSubmit}
      data-testid="login-form"
      noValidate
      method="post"
      action={`/api/login?locale=${locale}`}
    >
      <label>
        {t("login.username")}
        <input
          name="username"
          autoComplete="username"
          required
          data-testid="login-username"
        />
      </label>
      <label>
        {t("login.password")}
        <input
          name="password"
          type="password"
          autoComplete="current-password"
          required
          data-testid="login-password"
        />
      </label>
      <label className="option">
        <input name="remember" type="checkbox" data-testid="login-remember" />{" "}
        {t("login.remember")}
      </label>
      <input type="hidden" name="locale" value={locale} />
      <button
        type="submit"
        className="primary"
        disabled={submitting}
        data-testid="login-submit"
      >
        {submitting ? t("login.loading") : t("login.submit")}
      </button>
      <div aria-live="polite" className="status">
        {error ? (
          <p role="alert" className="error" data-testid="login-error">
            {error}
          </p>
        ) : null}
      </div>
      <noscript>
        <p className="muted">{t("login.description")}</p>
      </noscript>
    </form>
  );
}
