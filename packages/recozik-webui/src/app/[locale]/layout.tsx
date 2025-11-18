import { ReactNode } from "react";
import { SkipLink } from "../../components/SkipLink";
import { Locale, messages } from "../../i18n/messages";
import { isSupportedLocale } from "../../lib/constants";

interface Props {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}

function normalizeLocale(raw: string): Locale {
  return (isSupportedLocale(raw) ? raw : "en") as Locale;
}

export default async function LocaleLayout({ children, params }: Props) {
  const resolved = await params;
  const locale = normalizeLocale(resolved.locale);
  const skipLinkLabel = messages[locale]["skip.link"];
  return (
    <>
      <SkipLink label={skipLinkLabel} />
      <div id="main-content" tabIndex={-1}>
        {children}
      </div>
    </>
  );
}
