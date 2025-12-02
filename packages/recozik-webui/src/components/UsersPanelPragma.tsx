import { createUserAction } from "../app/actions-users";
import { Locale, messages } from "../i18n/messages";
import { UserResponse } from "../lib/api";

interface Props {
  locale: Locale;
  users: UserResponse[];
  status?: string | null;
  error?: string | null;
  fieldErrors?: Record<string, string> | undefined;
}

function t(locale: Locale, key: keyof typeof messages.en): string {
  return messages[locale][key] ?? key;
}

export default function UsersPanelPragma({
  locale,
  users,
  status,
  error,
  fieldErrors,
}: Props) {
  const usernameError = fieldErrors?.username;
  const emailError = fieldErrors?.email;
  const passwordError = fieldErrors?.password;

  return (
    <section className="panel" aria-labelledby="users-pragma-title">
      <h2 id="users-pragma-title">{t(locale, "users.title")}</h2>
      <p className="muted">{t(locale, "users.lead")}</p>

      <div className="table-wrapper">
        <table data-testid="admin-user-table">
          <caption className="sr-only">{t(locale, "users.title")}</caption>
          <thead>
            <tr>
              <th scope="col">{t(locale, "users.table.username")}</th>
              <th scope="col">{t(locale, "users.table.email")}</th>
              <th scope="col">{t(locale, "users.table.roles")}</th>
              <th scope="col">{t(locale, "users.table.features")}</th>
              <th scope="col">{t(locale, "users.table.status")}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.username}</td>
                <td>{user.email}</td>
                <td>{user.roles.join(", ") || "—"}</td>
                <td>{user.allowed_features.join(", ") || "—"}</td>
                <td>
                  {user.is_active
                    ? t(locale, "users.status.active")
                    : t(locale, "users.status.inactive")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form
        className="stack"
        action={createUserAction}
        method="post"
        data-testid="user-form"
      >
        <h3>{t(locale, "users.form.createTitle")}</h3>
        <input type="hidden" name="locale" value={locale} />
        <div className="grid-2">
          <label>
            {t(locale, "users.form.username")}
            <input
              name="username"
              required
              aria-invalid={usernameError ? "true" : "false"}
              aria-describedby={
                usernameError ? "user-username-error" : undefined
              }
            />
            {usernameError ? (
              <p id="user-username-error" className="error" role="alert">
                {usernameError}
              </p>
            ) : null}
          </label>
          <label>
            {t(locale, "users.form.email")}
            <input
              name="email"
              type="email"
              required
              aria-invalid={emailError ? "true" : "false"}
              aria-describedby={emailError ? "user-email-error" : undefined}
            />
            {emailError ? (
              <p id="user-email-error" className="error" role="alert">
                {emailError}
              </p>
            ) : null}
          </label>
        </div>
        <div className="grid-2">
          <label>
            {t(locale, "users.form.password")}
            <input
              name="password"
              type="password"
              required
              aria-invalid={passwordError ? "true" : "false"}
              aria-describedby={
                passwordError ? "user-password-error" : undefined
              }
            />
            {passwordError ? (
              <p id="user-password-error" className="error" role="alert">
                {passwordError}
              </p>
            ) : null}
          </label>
          <label>
            {t(locale, "users.form.displayNameOptional")}
            <input name="display_name" />
          </label>
        </div>

        <fieldset>
          <legend>{t(locale, "users.form.roles")}</legend>
          <label className="option">
            <input type="checkbox" name="role" value="admin" /> Admin
          </label>
          <label className="option">
            <input type="checkbox" name="role" value="operator" /> Operator
          </label>
          <label className="option">
            <input type="checkbox" name="role" value="readonly" /> Readonly
          </label>
        </fieldset>

        <fieldset>
          <legend>{t(locale, "users.form.features")}</legend>
          <label className="option">
            <input
              type="checkbox"
              name="feature"
              value="identify"
              defaultChecked
            />
            Identify
          </label>
          <label className="option">
            <input type="checkbox" name="feature" value="rename" /> Rename
          </label>
          <label className="option">
            <input type="checkbox" name="feature" value="audd" /> AudD
          </label>
          <label className="option">
            <input type="checkbox" name="feature" value="musicbrainz_enrich" />{" "}
            MusicBrainz
          </label>
        </fieldset>

        <button type="submit" className="primary">
          {t(locale, "users.form.submit")}
        </button>
      </form>

      <div aria-live="polite" aria-atomic="true" className="status">
        {status ? (
          <p role="status" data-testid="user-status">
            {status}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="error" data-testid="user-error">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
