"use client";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { useI18n } from "../i18n/I18nProvider";
import { useToken } from "./TokenProvider";

export function NavigationBar() {
  const { token, clearToken } = useToken();
  const { t } = useI18n();

  if (!token) {
    return null;
  }

  return (
    <nav className="top-nav" aria-label="Main navigation">
      <ul className="nav-links">
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
        <button type="button" className="secondary small" onClick={clearToken}>
          {t("nav.disconnect")}
        </button>
      </div>
    </nav>
  );
}
