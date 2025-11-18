"use client";

import { I18nProvider } from "../i18n/I18nProvider";
import { TokenProvider } from "./TokenProvider";
import { WhoAmI } from "../lib/api";
import { isSupportedLocale } from "../lib/constants";

interface Props {
  locale: string;
  initialToken?: string | null;
  initialProfile?: WhoAmI | null;
  children: React.ReactNode;
}

export function Providers({
  children,
  locale,
  initialToken,
  initialProfile,
}: Props) {
  const normalized = isSupportedLocale(locale) ? locale : "en";
  return (
    <I18nProvider locale={normalized}>
      <TokenProvider
        initialToken={initialToken}
        initialProfile={initialProfile}
      >
        {children}
      </TokenProvider>
    </I18nProvider>
  );
}
