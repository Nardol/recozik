"use client";

import { useI18n } from "../i18n/I18nProvider";
import { FEATURE_LABELS, ROLE_LABELS } from "../i18n/labels";
import { useToken } from "./TokenProvider";
import { logoutAction } from "../app/actions";

export function ProfileCard() {
  const { profile } = useToken();
  const { t, locale } = useI18n();

  if (!profile) {
    return null;
  }

  const translatedRoles =
    profile.roles.length === 0
      ? "—"
      : profile.roles
          .map((role) => {
            const key = ROLE_LABELS[role];
            return key ? t(key) : role;
          })
          .join(", ");

  const translatedFeatures = profile.allowed_features
    .map((feature) => {
      const key = FEATURE_LABELS[feature];
      return key ? t(key) : feature;
    })
    .join(", ");

  return (
    <section className="panel" aria-live="polite">
      <div className="profile">
        <div>
          <p className="muted">{t("profile.signedInAs")}</p>
          <strong>{profile.display_name ?? profile.user_id}</strong>
          <p className="muted">
            {t("profile.roles")}: {translatedRoles}
          </p>
          <p className="muted">
            {t("profile.features")}: {translatedFeatures || "—"}
          </p>
        </div>
        <form action={logoutAction}>
          <input type="hidden" name="locale" value={locale} />
          <button type="submit" className="secondary">
            {t("profile.forget")}
          </button>
        </form>
      </div>
    </section>
  );
}
