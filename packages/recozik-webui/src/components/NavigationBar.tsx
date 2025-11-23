"use client";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { useI18n } from "../i18n/I18nProvider";
import { useToken } from "./TokenProvider";

export function NavigationBar() {
  const { profile } = useToken();
  const { t, locale } = useI18n();

  if (!profile) {
    return null;
  }

  return (
    <nav className="top-nav" aria-label="Main navigation">
      <ul className="nav-links" role="list">
        <li>
          <a href="#upload-section">{t("nav.upload")}</a>
        </li>
        <li>
          <a href="#jobs-section">{t("nav.jobs")}</a>
        </li>
        <li>
          <a href="#admin-section">{t("nav.admin")}</a>
        </li>
      </ul>
      <div className="nav-actions">
        <LanguageSwitcher />
        <form action="/auth/logout" method="post" data-testid="logout-form">
          <input type="hidden" name="locale" value={locale} />
          <button type="submit" className="secondary small">
            {t("nav.disconnect")}
          </button>
        </form>
      </div>
    </nav>
  );
}
