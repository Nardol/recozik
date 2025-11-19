import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import type { WhoAmI } from "../lib/api";
import { I18nProvider, type Locale } from "../i18n/I18nProvider";
import { TokenProvider } from "../components/TokenProvider";

interface RenderOptions {
  locale?: Locale;
  token?: string | null;
  profile?: WhoAmI | null;
}

export function renderWithProviders(
  ui: ReactElement,
  { locale = "en", token = null, profile = null }: RenderOptions = {},
) {
  return render(
    <I18nProvider locale={locale}>
      <TokenProvider initialToken={token} initialProfile={profile}>
        {ui}
      </TokenProvider>
    </I18nProvider>,
  );
}
