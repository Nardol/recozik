"use client";

import { useToken } from "./TokenProvider";

export function ProfileCard() {
  const { profile, clearToken, status } = useToken();

  if (!profile) {
    return null;
  }

  return (
    <section className="panel" aria-live="polite">
      <div className="profile">
        <div>
          <p className="muted">Signed in as</p>
          <strong>{profile.display_name ?? profile.user_id}</strong>
          <p className="muted">Roles: {profile.roles.join(", ") || "—"}</p>
          <p className="muted">
            Features: {profile.allowed_features.join(", ")}
          </p>
        </div>
        <button
          type="button"
          className="secondary"
          onClick={clearToken}
          disabled={status === "loading"}
        >
          Forget token
        </button>
      </div>
    </section>
  );
}
