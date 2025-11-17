"use client";

import { I18nProvider } from "../i18n/I18nProvider";
import { TokenProvider } from "./TokenProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <TokenProvider>{children}</TokenProvider>
    </I18nProvider>
  );
}
