"use client";

import { createContext, useCallback, useContext, useMemo } from "react";

import { Locale, MessageKey, messages } from "./messages";

type MessageValues = Record<string, string | number>;

interface I18nContextValue {
  locale: Locale;
  t: (key: MessageKey, values?: MessageValues) => string;
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

function format(template: string, values?: MessageValues): string {
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_, token: string) => {
    const replacement = values[token];
    return replacement === undefined ? "" : String(replacement);
  });
}

interface Props {
  locale: Locale;
  children: React.ReactNode;
}

export function I18nProvider({ children, locale }: Props) {
  const t = useCallback(
    (key: MessageKey, values?: MessageValues) =>
      format(messages[locale][key] ?? key, values),
    [locale],
  );

  const value = useMemo(
    () => ({
      locale,
      t,
    }),
    [locale, t],
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
