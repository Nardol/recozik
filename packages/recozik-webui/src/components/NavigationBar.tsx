"use client";

import { useToken } from "./TokenProvider";

export function NavigationBar() {
  const { token, clearToken } = useToken();

  if (!token) {
    return null;
  }

  return (
    <nav className="top-nav" aria-label="Primary">
      <ul className="nav-links">
        <li>
          <a href="#upload-section">Upload</a>
        </li>
        <li>
          <a href="#jobs-section">Jobs</a>
        </li>
        <li>
          <a href="#admin-section">Admin</a>
        </li>
      </ul>
      <div className="nav-actions">
        <button
          type="button"
          className="secondary small"
          onClick={clearToken}
        >
          Disconnect
        </button>
      </div>
    </nav>
  );
}
