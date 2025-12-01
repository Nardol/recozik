"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  TokenCreatePayload,
  TokenResponse,
  UserResponse,
  createToken,
  fetchAdminTokens,
  fetchUsers,
} from "../lib/api";
import { MessageKey, useI18n } from "../i18n/I18nProvider";
import { FEATURE_LABELS, ROLE_LABELS, QUOTA_LABELS } from "../i18n/labels";
import { useToken } from "./TokenProvider";

const FEATURE_OPTIONS: { key: string; labelKey: MessageKey }[] = [
  { key: "identify", labelKey: "feature.identify" },
  { key: "identify_batch", labelKey: "feature.identify_batch" },
  { key: "rename", labelKey: "feature.rename" },
  { key: "audd", labelKey: "feature.audd" },
  { key: "musicbrainz_enrich", labelKey: "feature.musicbrainz_enrich" },
];

const ROLE_OPTIONS: { key: string; labelKey: MessageKey }[] = [
  { key: "admin", labelKey: "role.admin" },
  { key: "operator", labelKey: "role.operator" },
  { key: "readonly", labelKey: "role.readonly" },
];

interface Props {
  sectionId?: string;
}

export function AdminTokenManager({ sectionId }: Props) {
  const { profile } = useToken();
  const { t } = useI18n();
  const isAdmin = profile?.roles.includes("admin");
  const [records, setRecords] = useState<TokenResponse[]>([]);
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const loadTokens = useCallback(async () => {
    if (!isAdmin) return;
    try {
      setLoading(true);
      const data = await fetchAdminTokens();
      setRecords(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  const loadUsers = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const data = await fetchUsers();
      setUsers(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadTokens();
    loadUsers();
  }, [loadTokens, loadUsers]);

  if (!isAdmin) {
    return null;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const allowed = FEATURE_OPTIONS.filter((feature) =>
      formData.getAll("feature").includes(feature.key),
    ).map((feature) => feature.key);
    const roles = ROLE_OPTIONS.filter((role) =>
      formData.getAll("role").includes(role.key),
    ).map((role) => role.key);

    const userIdStr = formData.get("user_id")?.toString() ?? "";
    const userId = parseInt(userIdStr, 10);
    if (isNaN(userId)) {
      setError(t("admin.error.invalidUser"));
      return;
    }

    const payload: TokenCreatePayload = {
      token: formData.get("token")?.toString() || undefined,
      user_id: userId,
      display_name: formData.get("display_name")?.toString() ?? "",
      roles,
      allowed_features: allowed,
      quota_limits: {
        acoustid_lookup: parseNullableNumber(formData.get("quota_acoustid")),
        musicbrainz_enrich: parseNullableNumber(
          formData.get("quota_musicbrainz"),
        ),
        audd_standard_lookup: parseNullableNumber(formData.get("quota_audd")),
      },
    };

    try {
      setSaving(true);
      setMessage(t("admin.status.saving"));
      setError(null);
      await createToken(payload);
      setMessage(t("admin.status.saved"));
      event.currentTarget.reset();
      await loadTokens();
    } catch (err) {
      setMessage("");
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const translateFeature = (value: string) => {
    const key = FEATURE_LABELS[value];
    return key ? t(key) : value;
  };

  const translateRole = (value: string) => {
    const key = ROLE_LABELS[value];
    return key ? t(key) : value;
  };

  const translateQuota = (value: string) => {
    const key = QUOTA_LABELS[value];
    return key ? t(key) : value;
  };

  return (
    <section id={sectionId} aria-labelledby="admin-title" className="panel">
      <h2 id="admin-title">{t("admin.title")}</h2>
      <p className="muted">{t("admin.lead")}</p>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("admin.table.user")}</th>
              <th scope="col">{t("admin.table.token")}</th>
              <th scope="col">{t("admin.table.features")}</th>
              <th scope="col">{t("admin.table.quotas")}</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr
                key={record.token}
                data-testid={`token-row-${record.user_id}`}
              >
                <td data-testid={`token-user-${record.user_id}`}>
                  <strong>{record.display_name}</strong>
                  <div className="muted">{record.user_id}</div>
                  <div className="muted">
                    {t("admin.table.rolesPrefix")}:{" "}
                    {record.roles.length
                      ? record.roles.map(translateRole).join(", ")
                      : "—"}
                  </div>
                </td>
                <td data-testid={`token-value-${record.user_id}`}>
                  <code>{record.token}</code>
                </td>
                <td data-testid={`token-features-${record.user_id}`}>
                  <ul>
                    {record.allowed_features.map((feature) => (
                      <li key={feature}>{translateFeature(feature)}</li>
                    ))}
                  </ul>
                </td>
                <td data-testid={`token-quotas-${record.user_id}`}>
                  <ul>
                    {Object.entries(record.quota_limits).map(
                      ([scope, value]) => (
                        <li key={scope}>
                          {translateQuota(scope)}: {value ?? "∞"}
                        </li>
                      ),
                    )}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form className="stack" onSubmit={handleSubmit} data-testid="token-form">
        <h3>{t("admin.form.title")}</h3>
        <div className="grid-2">
          <label>
            {t("admin.form.user")}
            <span className="field-hint">{t("admin.form.userHint")}</span>
            <select name="user_id" required data-testid="token-form-user">
              <option value="">{t("admin.form.selectUser")}</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name || user.username} ({user.email})
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("admin.form.displayName")}
            <span className="field-hint">
              {t("admin.form.displayNameHint")}
            </span>
            <input
              name="display_name"
              type="text"
              required
              data-testid="token-form-display-name"
            />
          </label>
        </div>
        <fieldset>
          <legend>{t("admin.form.rolesLegend")}</legend>
          <p className="field-hint">{t("admin.form.rolesHint")}</p>
          {ROLE_OPTIONS.map((role) => (
            <label key={role.key} className="option">
              <input type="checkbox" name="role" value={role.key} />
              {t(role.labelKey)}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>{t("admin.form.featuresLegend")}</legend>
          {FEATURE_OPTIONS.map((feature) => (
            <label key={feature.key} className="option">
              <input
                type="checkbox"
                name="feature"
                value={feature.key}
                defaultChecked={feature.key === "identify"}
              />
              {t(feature.labelKey)}
            </label>
          ))}
        </fieldset>
        <div className="grid-3">
          <label>
            {t("admin.form.acoustid")}
            <input
              name="quota_acoustid"
              type="number"
              min="0"
              placeholder="∞"
            />
          </label>
          <label>
            {t("admin.form.musicbrainz")}
            <input
              name="quota_musicbrainz"
              type="number"
              min="0"
              placeholder="∞"
            />
          </label>
          <label>
            {t("admin.form.audd")}
            <input name="quota_audd" type="number" min="0" placeholder="∞" />
          </label>
        </div>
        <details className="advanced">
          <summary>{t("admin.form.advanced")}</summary>
          <label>
            {t("admin.form.tokenOptional")}
            <input name="token" type="text" autoComplete="off" />
          </label>
        </details>
        <button
          type="submit"
          className="primary"
          disabled={loading || saving}
          data-testid="token-form-submit"
        >
          {saving ? t("admin.form.saving") : t("admin.form.save")}
        </button>
      </form>
      <div aria-live="polite" className="status">
        {message}
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

function parseNullableNumber(value: FormDataEntryValue | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
