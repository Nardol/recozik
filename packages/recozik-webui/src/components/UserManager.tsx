"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  UserResponse,
  RegisterUserPayload,
  UpdateUserPayload,
  SessionResponse,
  fetchUsers,
  registerUser,
  updateUser,
  deleteUser,
  adminResetPassword,
  fetchUserSessions,
  revokeUserSessions,
} from "../lib/api";
import { MessageKey, useI18n } from "../i18n/I18nProvider";
import { FEATURE_LABELS, ROLE_LABELS } from "../i18n/labels";
import { useToken } from "./TokenProvider";
import { useModalAccessibility } from "../hooks/useModalAccessibility";

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

type ModalMode = "create" | "edit" | "sessions" | "reset-password" | null;

function parseNullableNumber(value: FormDataEntryValue | null): number | null {
  if (!value || value === "") return null;
  const parsed = Number(value);
  return isNaN(parsed) ? null : parsed;
}

export function UserManager({ sectionId }: Props) {
  const { profile } = useToken();
  const { t } = useI18n();
  const isAdmin = profile?.roles.includes("admin");

  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null);
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [saving, setSaving] = useState(false);

  // Accessibility hooks for modals
  const { modalRef: userFormModalRef } = useModalAccessibility({
    isOpen: modalMode === "create" || modalMode === "edit",
    onClose: () => setModalMode(null),
  });

  const { modalRef: passwordModalRef } = useModalAccessibility({
    isOpen: modalMode === "reset-password",
    onClose: () => setModalMode(null),
  });

  const { modalRef: sessionsModalRef } = useModalAccessibility({
    isOpen: modalMode === "sessions",
    onClose: () => setModalMode(null),
  });

  const loadUsers = useCallback(async () => {
    if (!isAdmin) return;
    try {
      setLoading(true);
      const data = await fetchUsers();
      setUsers(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleCreateUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);

    const allowed = FEATURE_OPTIONS.filter((feature) =>
      formData.getAll("feature").includes(feature.key),
    ).map((feature) => feature.key);
    const roles = ROLE_OPTIONS.filter((role) =>
      formData.getAll("role").includes(role.key),
    ).map((role) => role.key);

    const payload: RegisterUserPayload = {
      username: formData.get("username")?.toString() ?? "",
      email: formData.get("email")?.toString() ?? "",
      display_name: formData.get("display_name")?.toString() || null,
      password: formData.get("password")?.toString() ?? "",
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
      setError(null);
      await registerUser(payload);
      setModalMode(null);
      await loadUsers();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedUser) return;

    const formData = new FormData(event.currentTarget);
    const allowed = FEATURE_OPTIONS.filter((feature) =>
      formData.getAll("feature").includes(feature.key),
    ).map((feature) => feature.key);
    const roles = ROLE_OPTIONS.filter((role) =>
      formData.getAll("role").includes(role.key),
    ).map((role) => role.key);

    const payload: UpdateUserPayload = {
      email: formData.get("email")?.toString() || null,
      display_name: formData.get("display_name")?.toString() || null,
      is_active: formData.get("is_active") === "on",
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
      setError(null);
      await updateUser(selectedUser.id, payload);
      setModalMode(null);
      setSelectedUser(null);
      await loadUsers();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteUser = async (user: UserResponse) => {
    if (
      !confirm(t("users.delete.confirm").replace("{username}", user.username))
    ) {
      return;
    }

    try {
      await deleteUser(user.id);
      await loadUsers();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleResetPassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedUser) return;

    const formData = new FormData(event.currentTarget);
    const newPassword = formData.get("new_password")?.toString() ?? "";

    try {
      setSaving(true);
      setError(null);
      await adminResetPassword(selectedUser.id, { new_password: newPassword });
      setModalMode(null);
      setSelectedUser(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleViewSessions = async (user: UserResponse) => {
    setSelectedUser(user);
    setModalMode("sessions");
    try {
      const data = await fetchUserSessions(user.id);
      setSessions(data);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleRevokeAllSessions = async () => {
    if (!selectedUser) return;

    try {
      await revokeUserSessions(selectedUser.id);
      setSessions([]);
    } catch (err) {
      setError((err as Error).message);
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

  if (!isAdmin) {
    return null;
  }

  return (
    <section id={sectionId} aria-labelledby="users-title" className="panel">
      <h2 id="users-title">{t("users.title")}</h2>
      <p className="muted">{t("users.lead")}</p>

      <button
        type="button"
        onClick={() => setModalMode("create")}
        className="btn btn-primary"
      >
        {t("users.createButton")}
      </button>

      {error && (
        <div role="alert" className="error-message">
          {error}
        </div>
      )}

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("users.table.username")}</th>
              <th scope="col">{t("users.table.email")}</th>
              <th scope="col">{t("users.table.roles")}</th>
              <th scope="col">{t("users.table.features")}</th>
              <th scope="col">{t("users.table.status")}</th>
              <th scope="col">{t("users.table.created")}</th>
              <th scope="col">{t("users.table.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: "center" }}>
                  {loading ? t("users.loading") : t("users.empty")}
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.display_name || user.username}</strong>
                    {user.display_name && (
                      <div className="muted">{user.username}</div>
                    )}
                  </td>
                  <td>{user.email}</td>
                  <td>
                    {user.roles.length
                      ? user.roles.map(translateRole).join(", ")
                      : "—"}
                  </td>
                  <td>
                    {user.allowed_features.length
                      ? user.allowed_features.map(translateFeature).join(", ")
                      : "—"}
                  </td>
                  <td>
                    {user.is_active
                      ? t("users.status.active")
                      : t("users.status.inactive")}
                  </td>
                  <td>{new Date(user.created_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedUser(user);
                        setModalMode("edit");
                      }}
                      className="btn-link"
                    >
                      {t("users.action.edit")}
                    </button>
                    {" | "}
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedUser(user);
                        setModalMode("reset-password");
                      }}
                      className="btn-link"
                    >
                      {t("users.action.resetPassword")}
                    </button>
                    {" | "}
                    <button
                      type="button"
                      onClick={() => handleViewSessions(user)}
                      className="btn-link"
                    >
                      {t("users.action.sessions")}
                    </button>
                    {" | "}
                    <button
                      type="button"
                      onClick={() => handleDeleteUser(user)}
                      className="btn-link btn-danger"
                    >
                      {t("users.action.delete")}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Create/Edit User Modal */}
      {(modalMode === "create" || modalMode === "edit") && (
        <div className="modal-overlay" onClick={() => setModalMode(null)}>
          <div
            ref={userFormModalRef}
            className="modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="user-form-title"
            tabIndex={-1}
          >
            <h3 id="user-form-title">
              {modalMode === "create"
                ? t("users.form.createTitle")
                : t("users.form.editTitle")}
            </h3>
            <form
              onSubmit={
                modalMode === "create" ? handleCreateUser : handleUpdateUser
              }
            >
              {modalMode === "create" && (
                <>
                  <label>
                    {t("users.form.username")}
                    <input
                      type="text"
                      name="username"
                      required
                      autoComplete="username"
                    />
                  </label>
                  <label>
                    {t("users.form.email")}
                    <input
                      type="email"
                      name="email"
                      required
                      autoComplete="email"
                    />
                  </label>
                  <label>
                    {t("users.form.displayNameOptional")}
                    <input
                      type="text"
                      name="display_name"
                      autoComplete="name"
                    />
                  </label>
                  <label>
                    {t("users.form.password")}
                    <input
                      type="password"
                      name="password"
                      required
                      autoComplete="new-password"
                    />
                    <div className="muted">{t("users.form.passwordHint")}</div>
                  </label>
                </>
              )}

              {modalMode === "edit" && (
                <>
                  <p className="muted">
                    {t("users.form.editing")}{" "}
                    <strong>{selectedUser?.username}</strong>
                  </p>
                  <label>
                    {t("users.form.email")}
                    <input
                      type="email"
                      name="email"
                      defaultValue={selectedUser?.email ?? ""}
                      autoComplete="email"
                    />
                  </label>
                  <label>
                    {t("users.form.displayName")}
                    <input
                      type="text"
                      name="display_name"
                      defaultValue={selectedUser?.display_name ?? ""}
                      autoComplete="name"
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      name="is_active"
                      defaultChecked={selectedUser?.is_active ?? true}
                    />
                    {t("users.form.active")}
                  </label>
                </>
              )}

              <fieldset>
                <legend>{t("users.form.roles")}</legend>
                {ROLE_OPTIONS.map((role) => (
                  <label key={role.key}>
                    <input
                      type="checkbox"
                      name="role"
                      value={role.key}
                      defaultChecked={
                        modalMode === "edit"
                          ? selectedUser?.roles.includes(role.key)
                          : role.key === "readonly"
                      }
                    />
                    {t(role.labelKey)}
                  </label>
                ))}
              </fieldset>

              <fieldset>
                <legend>{t("users.form.features")}</legend>
                {FEATURE_OPTIONS.map((feature) => (
                  <label key={feature.key}>
                    <input
                      type="checkbox"
                      name="feature"
                      value={feature.key}
                      defaultChecked={
                        modalMode === "edit" &&
                        selectedUser?.allowed_features.includes(feature.key)
                      }
                    />
                    {t(feature.labelKey)}
                  </label>
                ))}
              </fieldset>

              <fieldset>
                <legend>{t("users.form.quotas")}</legend>
                <div className="muted">{t("users.form.quotasHint")}</div>
                <label>
                  {t("users.form.quotaAcoustid")}
                  <input
                    type="number"
                    name="quota_acoustid"
                    defaultValue={
                      modalMode === "edit"
                        ? (selectedUser?.quota_limits?.acoustid_lookup ?? "")
                        : ""
                    }
                  />
                </label>
                <label>
                  {t("users.form.quotaMusicbrainz")}
                  <input
                    type="number"
                    name="quota_musicbrainz"
                    defaultValue={
                      modalMode === "edit"
                        ? (selectedUser?.quota_limits?.musicbrainz_enrich ?? "")
                        : ""
                    }
                  />
                </label>
                <label>
                  {t("users.form.quotaAudd")}
                  <input
                    type="number"
                    name="quota_audd"
                    defaultValue={
                      modalMode === "edit"
                        ? (selectedUser?.quota_limits?.audd_standard_lookup ??
                          "")
                        : ""
                    }
                  />
                </label>
              </fieldset>

              <div className="modal-actions">
                <button type="submit" disabled={saving}>
                  {saving ? t("users.form.submitting") : t("users.form.submit")}
                </button>
                <button
                  type="button"
                  onClick={() => setModalMode(null)}
                  disabled={saving}
                >
                  {t("users.form.cancel")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reset Password Modal */}
      {modalMode === "reset-password" && selectedUser && (
        <div className="modal-overlay" onClick={() => setModalMode(null)}>
          <div
            ref={passwordModalRef}
            className="modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-password-title"
            tabIndex={-1}
          >
            <h3 id="reset-password-title">
              {t("users.resetPassword.title").replace(
                "{username}",
                selectedUser.username,
              )}
            </h3>
            <form onSubmit={handleResetPassword}>
              <label>
                {t("users.resetPassword.newPassword")}
                <input
                  type="password"
                  name="new_password"
                  required
                  autoComplete="new-password"
                />
                <div className="muted">{t("users.form.passwordHint")}</div>
              </label>
              <div className="modal-actions">
                <button type="submit" disabled={saving}>
                  {saving
                    ? t("users.form.submitting")
                    : t("users.resetPassword.submit")}
                </button>
                <button
                  type="button"
                  onClick={() => setModalMode(null)}
                  disabled={saving}
                >
                  {t("users.form.cancel")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Sessions Modal */}
      {modalMode === "sessions" && selectedUser && (
        <div className="modal-overlay" onClick={() => setModalMode(null)}>
          <div
            ref={sessionsModalRef}
            className="modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="sessions-title"
            tabIndex={-1}
          >
            <h3 id="sessions-title">
              {t("users.sessions.title").replace(
                "{username}",
                selectedUser.username,
              )}
            </h3>
            {sessions.length === 0 ? (
              <p>{t("users.sessions.empty")}</p>
            ) : (
              <>
                <table>
                  <thead>
                    <tr>
                      <th>{t("users.sessions.table.created")}</th>
                      <th>{t("users.sessions.table.expires")}</th>
                      <th>{t("users.sessions.table.remember")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((session) => (
                      <tr key={session.id}>
                        <td>{new Date(session.created_at).toLocaleString()}</td>
                        <td>
                          {new Date(
                            session.refresh_expires_at,
                          ).toLocaleString()}
                        </td>
                        <td>
                          {session.remember ? t("common.yes") : t("common.no")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button
                  type="button"
                  onClick={handleRevokeAllSessions}
                  className="btn-danger"
                >
                  {t("users.sessions.revokeAll")}
                </button>
              </>
            )}
            <div className="modal-actions">
              <button type="button" onClick={() => setModalMode(null)}>
                {t("users.sessions.close")}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
