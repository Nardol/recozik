import { TokenResponse, UserResponse } from "../lib/api";
import { Locale, messages } from "../i18n/messages";
import { createTokenAction } from "../app/actions-admin";

interface Props {
  locale: Locale;
  tokens: TokenResponse[];
  users: UserResponse[];
  status?: string | null;
  error?: string | null;
  fieldErrors?: Record<string, string> | undefined;
}

function t(locale: Locale, key: keyof typeof messages.en): string {
  return messages[locale][key] ?? key;
}

export default function AdminTokenPanelPragma({
  locale,
  tokens,
  users,
  status,
  error,
  fieldErrors,
}: Props) {
  const userError = fieldErrors?.user_id;
  const displayError = fieldErrors?.display_name;
  return (
    <section className="panel" aria-labelledby="admin-pragma-title">
      <h2 id="admin-pragma-title">{t(locale, "admin.title")}</h2>
      <p className="muted">{t(locale, "admin.lead")}</p>

      <div className="table-wrapper">
        <table data-testid="admin-token-table">
          <caption className="sr-only">{t(locale, "admin.title")}</caption>
          <thead>
            <tr>
              <th scope="col">{t(locale, "admin.table.user")}</th>
              <th scope="col">{t(locale, "admin.table.token")}</th>
              <th scope="col">{t(locale, "admin.table.roles")}</th>
              <th scope="col">{t(locale, "admin.table.features")}</th>
              <th scope="col">{t(locale, "admin.table.quotas")}</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((record) => (
              <tr key={record.token}>
                <td>
                  <strong>{record.display_name}</strong>
                  <div className="muted">{record.user_id}</div>
                </td>
                <td>
                  <code>{record.token}</code>
                </td>
                <td>{record.roles?.length ? record.roles.join(", ") : "—"}</td>
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

      <form
        className="stack"
        action={createTokenAction}
        method="post"
        data-testid="token-form"
      >
        <h3>{t(locale, "admin.form.title")}</h3>
        <input type="hidden" name="locale" value={locale} />
        <div className="grid-2">
          <label>
            {t(locale, "admin.form.user")}
            <select
              name="user_id"
              required
              aria-invalid={userError ? "true" : "false"}
              aria-describedby={userError ? "user-error" : undefined}
            >
              <option value="">{t(locale, "admin.form.selectUser")}</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name || user.username} ({user.email})
                </option>
              ))}
            </select>
            {userError ? (
              <p id="user-error" className="error" role="alert">
                {userError}
              </p>
            ) : null}
          </label>
          <label>
            {t(locale, "admin.form.displayName")}
            <input
              name="display_name"
              type="text"
              required
              aria-invalid={displayError ? "true" : "false"}
              aria-describedby={displayError ? "display-error" : undefined}
            />
            {displayError ? (
              <p id="display-error" className="error" role="alert">
                {displayError}
              </p>
            ) : null}
          </label>
        </div>

        <fieldset>
          <legend>{t(locale, "admin.form.rolesLegend")}</legend>
          <label className="option">
            <input type="checkbox" name="role" value="admin" />{" "}
            {t(locale, "admin.form.role.admin")}
          </label>
          <label className="option">
            <input type="checkbox" name="role" value="operator" />{" "}
            {t(locale, "admin.form.role.operator")}
          </label>
          <label className="option">
            <input type="checkbox" name="role" value="readonly" />{" "}
            {t(locale, "admin.form.role.readonly")}
          </label>
        </fieldset>

        <fieldset>
          <legend>{t(locale, "admin.form.featuresLegend")}</legend>
          <label className="option">
            <input
              type="checkbox"
              name="feature"
              value="identify"
              defaultChecked
            />
            {t(locale, "admin.form.feature.identify")}
          </label>
          <label className="option">
            <input type="checkbox" name="feature" value="identify_batch" />{" "}
            {t(locale, "admin.form.feature.batch")}
          </label>
          <label className="option">
            <input type="checkbox" name="feature" value="rename" />{" "}
            {t(locale, "admin.form.feature.rename")}
          </label>
          <label className="option">
            <input type="checkbox" name="feature" value="audd" />{" "}
            {t(locale, "admin.form.feature.audd")}
          </label>
          <label className="option">
            <input type="checkbox" name="feature" value="musicbrainz_enrich" />{" "}
            {t(locale, "admin.form.feature.musicbrainz")}
          </label>
        </fieldset>

        <div className="grid-3">
          <label>
            {t(locale, "admin.form.acoustid")}
            <input
              name="quota_acoustid"
              type="number"
              min="0"
              placeholder="∞"
            />
          </label>
          <label>
            {t(locale, "admin.form.musicbrainz")}
            <input
              name="quota_musicbrainz"
              type="number"
              min="0"
              placeholder="∞"
            />
          </label>
          <label>
            {t(locale, "admin.form.audd")}
            <input name="quota_audd" type="number" min="0" placeholder="∞" />
          </label>
        </div>

        <label>
          {t(locale, "admin.form.tokenOptional")}
          <input name="token" type="text" autoComplete="off" />
        </label>

        <button type="submit" className="primary">
          {t(locale, "admin.form.save")}
        </button>
      </form>

      <div aria-live="polite" aria-atomic="true" className="status">
        {status ? (
          <p role="status" data-testid="token-status">
            {status}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="error" data-testid="token-error">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
