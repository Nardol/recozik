"use client";

import { useI18n } from "../i18n/I18nProvider";

export function SkipLink() {
  const { t } = useI18n();
  return (
    <a className="visually-hidden" href="#main-content">
      {t("skip.link")}
    </a>
  );
}
