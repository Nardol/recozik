"use server";

import { redirect } from "next/navigation";
import { serverFetch } from "../lib/server/api";

/**
 * Server action to create a new user account from a noscript HTML form.
 * Expects string fields in FormData; redirects with status or error codes.
 */
export async function createUserAction(formData: FormData) {
  const readString = (key: string, fallback = "") => {
    const value = formData.get(key);
    return typeof value === "string" ? value : fallback;
  };

  const locale = readString("locale", "en");
  const username = readString("username").trim();
  const email = readString("email").trim();
  const password = readString("password");
  const display_name = readString("display_name").trim();
  const roles = formData
    .getAll("role")
    .map((v) => (typeof v === "string" ? v : ""))
    .filter(Boolean);
  const allowed_features = formData
    .getAll("feature")
    .map((v) => (typeof v === "string" ? v : ""))
    .filter(Boolean);

  if (!username || !email || !password) {
    redirect(`/${locale}?user_error=missing_fields`);
  }

  try {
    await serverFetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        email,
        display_name: display_name || null,
        password,
        roles,
        allowed_features,
        quota_limits: {},
      }),
    });
    redirect(`/${locale}?user_status=created`);
  } catch (error) {
    const message = (error as Error).message?.slice(0, 200) || "server_error";
    redirect(`/${locale}?user_error=${encodeURIComponent(message)}`);
  }
}
