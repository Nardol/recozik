"use client";

import { useEffect } from "react";
import { useI18n } from "../i18n/I18nProvider";

export function LangUpdater() {
  const { locale } = useI18n();

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
  }, [locale]);

  return null;
}
