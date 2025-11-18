"use client";

import { useFormState, useFormStatus } from "react-dom";
import { useI18n } from "../i18n/I18nProvider";
import { loginAction } from "../app/actions";
import { DEFAULT_LOGIN_STATE } from "../app/action-defaults";

function SubmitButton({
  savingLabel,
  idleLabel,
}: {
  savingLabel: string;
  idleLabel: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="primary" disabled={pending}>
      {pending ? savingLabel : idleLabel}
    </button>
  );
}

export function TokenForm() {
  const { t, locale } = useI18n();
  const [state, formAction] = useFormState(loginAction, DEFAULT_LOGIN_STATE);

  return (
    <section aria-labelledby="token-form-title" className="panel">
      <h2 id="token-form-title">{t("tokenForm.title")}</h2>
      <p className="muted">{t("tokenForm.description")}</p>
      <form action={formAction} className="stack">
        <input type="hidden" name="locale" value={locale} />
        <label htmlFor="token-input">{t("tokenForm.label")}</label>
        <input
          id="token-input"
          name="token"
          type="password"
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          aria-describedby="token-help"
          required
        />
        <p id="token-help" className="muted">
          {t("tokenForm.help")}
        </p>
        <label className="option" htmlFor="remember-token">
          <input id="remember-token" name="remember" type="checkbox" />
          {t("tokenForm.remember")}
        </label>
        <SubmitButton
          savingLabel={t("tokenForm.saving")}
          idleLabel={t("tokenForm.save")}
        />
        {state.message ? (
          <p
            role={state.status === "error" ? "alert" : "status"}
            className={state.status === "error" ? "error" : "status"}
          >
            {state.message}
          </p>
        ) : null}
      </form>
    </section>
  );
}
