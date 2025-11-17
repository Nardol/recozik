"use client";

import { Locale, useI18n } from "../i18n/I18nProvider";

const OPTIONS: Locale[] = ["en", "fr"];

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();

  return (
    <label className="language-switcher">
      <span className="visually-hidden">{t("nav.language")}</span>
      <select
        aria-label={t("nav.language")}
        value={locale}
        onChange={(event) => setLocale(event.target.value as Locale)}
      >
        {OPTIONS.map((option) => (
          <option key={option} value={option}>
            {t(option === "en" ? "language.en" : "language.fr")}
          </option>
        ))}
      </select>
    </label>
  );
}
