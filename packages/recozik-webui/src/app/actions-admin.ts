"use server";

import { redirect } from "next/navigation";
import { serverFetch } from "../lib/server/api";

function parseNullableNumber(value: FormDataEntryValue | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function createTokenAction(formData: FormData) {
  const locale = (formData.get("locale") || "en").toString();
  try {
    const allowed = formData.getAll("feature").map((v) => v.toString());
    const roles = formData.getAll("role").map((v) => v.toString());
    const userIdStr = formData.get("user_id")?.toString() ?? "";
    const user_id = Number(userIdStr);
    if (!Number.isFinite(user_id)) {
      return redirect(`/${locale}?token_error=invalid_user`);
    }
    const display_name = formData.get("display_name")?.toString().trim() ?? "";
    if (!display_name) {
      return redirect(`/${locale}?token_error=missing_display`);
    }
    const payload = {
      token: formData.get("token")?.toString() || undefined,
      user_id,
      display_name,
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
    await serverFetch("/admin/tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    redirect(`/${locale}?token_status=created`);
  } catch (error: unknown) {
    // Let Next.js handle redirect errors
    if (
      error &&
      typeof error === "object" &&
      "digest" in error &&
      typeof (error as { digest?: string }).digest === "string" &&
      (error as { digest?: string }).digest?.startsWith("NEXT_REDIRECT")
    ) {
      throw error;
    }
    const message = (error as Error).message?.slice(0, 200) || "server_error";
    redirect(`/${locale}?token_error=${encodeURIComponent(message)}`);
  }
}
