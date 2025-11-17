"use client";

import { usePathname, useRouter } from "next/navigation";
import { Locale, useI18n } from "../i18n/I18nProvider";

const OPTIONS: Locale[] = ["en", "fr"];

export function LanguageSwitcher() {
  const { locale, t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();

  const handleChange = (value: Locale) => {
    const segments = pathname.split("/").filter(Boolean);
    if (segments.length === 0) {
      router.push(`/${value}`);
      return;
    }
    segments[0] = value;
    router.push(`/${segments.join("/")}`);
  };

  return (
    <label className="language-switcher">
      <span className="visually-hidden">{t("nav.language")}</span>
      <select
        aria-label={t("nav.language")}
        value={locale}
        onChange={(event) => handleChange(event.target.value as Locale)}
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
