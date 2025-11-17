"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  TokenCreatePayload,
  TokenResponse,
  createToken,
  fetchAdminTokens,
} from "../lib/api";
import { useToken } from "./TokenProvider";

const FEATURE_OPTIONS = [
  { key: "identify", label: "Identify" },
  { key: "identify_batch", label: "Batch Identify" },
  { key: "rename", label: "Rename" },
  { key: "audd", label: "AudD" },
  { key: "musicbrainz_enrich", label: "MusicBrainz" },
];

const ROLE_OPTIONS = [
  { key: "admin", label: "Admin" },
  { key: "operator", label: "Operator" },
  { key: "readonly", label: "Readonly" },
];

interface Props {
  sectionId?: string;
}

export function AdminTokenManager({ sectionId }: Props) {
  const { token, profile } = useToken();
  const isAdmin = profile?.roles.includes("admin");
  const [records, setRecords] = useState<TokenResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const loadTokens = useCallback(async () => {
    if (!token || !isAdmin) return;
    try {
      setLoading(true);
      const data = await fetchAdminTokens(token);
      setRecords(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token, isAdmin]);

  useEffect(() => {
    loadTokens();
  }, [loadTokens]);

  if (!isAdmin) {
    return null;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    const formData = new FormData(event.currentTarget);
    const allowed = FEATURE_OPTIONS.filter((feature) =>
      formData.getAll("feature").includes(feature.key),
    ).map((feature) => feature.key);
    const roles = ROLE_OPTIONS.filter((role) =>
      formData.getAll("role").includes(role.key),
    ).map((role) => role.key);

    const payload: TokenCreatePayload = {
      token: formData.get("token")?.toString() || undefined,
      user_id: formData.get("user_id")?.toString() ?? "",
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
      setMessage("Saving token…");
      setError(null);
      await createToken(token, payload);
      setMessage("Token saved.");
      event.currentTarget.reset();
      await loadTokens();
    } catch (err) {
      setMessage("");
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section id={sectionId} aria-labelledby="admin-title" className="panel">
      <h2 id="admin-title">Admin · Token management</h2>
      <p className="muted">
        Create or update tokens, toggle AudD access, and tune quota policies.
      </p>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th scope="col">User</th>
              <th scope="col">Token</th>
              <th scope="col">Features</th>
              <th scope="col">Quotas</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.token}>
                <td>
                  <strong>{record.display_name}</strong>
                  <div className="muted">{record.user_id}</div>
                  <div className="muted">
                    Roles: {record.roles.join(", ") || "—"}
                  </div>
                </td>
                <td>
                  <code>{record.token}</code>
                </td>
                <td>
                  <ul>
                    {record.allowed_features.map((feature) => (
                      <li key={feature}>{feature}</li>
                    ))}
                  </ul>
                </td>
                <td>
                  <ul>
                    {Object.entries(record.quota_limits).map(
                      ([scope, value]) => (
                        <li key={scope}>
                          {scope}: {value ?? "∞"}
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

      <form className="stack" onSubmit={handleSubmit}>
        <h3>Create or update a token</h3>
        <div className="grid-2">
          <label>
            User ID
            <span className="field-hint">
              Used in logs and quota entries. Keep it short.
            </span>
            <input name="user_id" type="text" required />
          </label>
          <label>
            Display name
            <input name="display_name" type="text" required />
          </label>
        </div>
        <fieldset>
          <legend>Roles</legend>
          <p className="field-hint">
            Assign capabilities such as admin access or read-only usage.
          </p>
          {ROLE_OPTIONS.map((role) => (
            <label key={role.key} className="option">
              <input type="checkbox" name="role" value={role.key} />
              {role.label}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Allowed features</legend>
          {FEATURE_OPTIONS.map((feature) => (
            <label key={feature.key} className="option">
              <input
                type="checkbox"
                name="feature"
                value={feature.key}
                defaultChecked={feature.key === "identify"}
              />
              {feature.label}
            </label>
          ))}
        </fieldset>
        <div className="grid-3">
          <label>
            AcoustID quota
            <input
              name="quota_acoustid"
              type="number"
              min="0"
              placeholder="∞"
            />
          </label>
          <label>
            MusicBrainz quota
            <input
              name="quota_musicbrainz"
              type="number"
              min="0"
              placeholder="∞"
            />
          </label>
          <label>
            AudD quota
            <input name="quota_audd" type="number" min="0" placeholder="∞" />
          </label>
        </div>
        <details className="advanced">
          <summary>Advanced options</summary>
          <label>
            Token (optional, leave blank to auto-generate)
            <input name="token" type="text" autoComplete="off" />
          </label>
        </details>
        <button type="submit" className="primary" disabled={loading || saving}>
          {saving ? "Saving…" : "Save token"}
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
