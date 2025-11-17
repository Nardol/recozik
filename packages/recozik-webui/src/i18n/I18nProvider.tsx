"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { Locale, MessageKey, messages } from "./messages";

type MessageValues = Record<string, string | number>;

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, values?: MessageValues) => string;
}

const I18N_STORAGE_KEY = "recozik-webui-locale";
const SUPPORTED_LOCALES: Locale[] = ["en", "fr"];

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

function resolveLocale(candidate?: string | null): Locale {
  if (!candidate) {
    return "en";
  }
  const base = candidate.split("-")[0]?.toLowerCase();
  return (SUPPORTED_LOCALES.find((locale) => locale === base) ??
    "en") as Locale;
}

function format(template: string, values?: MessageValues): string {
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_, token: string) => {
    const replacement = values[token];
    return replacement === undefined ? "" : String(replacement);
  });
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const stored = window.localStorage.getItem(I18N_STORAGE_KEY);
    const detected = resolveLocale(stored ?? navigator.language);
    setLocaleState(detected);
  }, []);

  const setLocale = useCallback((value: Locale) => {
    setLocaleState(value);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(I18N_STORAGE_KEY, value);
    }
  }, []);

  const t = useCallback(
    (key: MessageKey, values?: MessageValues) =>
      format(messages[locale][key] ?? key, values),
    [locale],
  );

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t,
    }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return context;
}

export type { Locale, MessageKey } from "./messages";
