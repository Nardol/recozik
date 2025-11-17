"use client";

import { FormEvent, useState } from "react";
import { useToken } from "./TokenProvider";

export function TokenForm() {
  const { setToken, status } = useToken();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      if (!value.trim()) {
        setError("Please provide an API token.");
        return;
      }
      setToken(value.trim());
      setValue("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save token.");
    }
  };

  return (
    <section aria-labelledby="token-form-title" className="panel">
      <h2 id="token-form-title">Connect with an API token</h2>
      <p className="muted">
        Tokens are managed in the CLI or via the admin API.
      </p>
      <form onSubmit={handleSubmit} className="stack">
        <label htmlFor="token-input">Token</label>
        <input
          id="token-input"
          name="token"
          type="password"
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-describedby="token-help"
          disabled={status === "loading"}
          required
        />
        <p id="token-help" className="muted">
          Your token is stored locally in the browser and never shared with
          Recozik.
        </p>
        <button
          type="submit"
          className="primary"
          disabled={status === "loading"}
        >
          {status === "loading" ? "Validating…" : "Save token"}
        </button>
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : null}
      </form>
    </section>
  );
}
