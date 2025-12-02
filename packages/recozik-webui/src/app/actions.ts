"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { serverCreateJob } from "../lib/server/jobs";
import { serverFetch } from "../lib/server/api";
import type { LoginState, UploadState } from "./action-types";

export async function loginAction(
  _prevState: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const username = (formData.get("username") || "").toString().trim();
  const password = (formData.get("password") || "").toString();
  const locale = (formData.get("locale") || "en").toString();
  const remember = formData.get("remember") === "on";

  if (!username || !password) {
    redirect(`/${locale}?login_error=missing_credentials`);
  }

  try {
    await serverFetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, remember }),
    });
    revalidatePath(`/${locale}`);
    redirect(`/${locale}?login_status=ok`);
  } catch (_error) {
    void _error;
    const code = "invalid_credentials";
    redirect(`/${locale}?login_error=${code}`);
  }
}

export async function logoutAction(formData: FormData) {
  const locale = (formData.get("locale") || "en").toString();
  try {
    await serverFetch("/auth/logout", { method: "POST" });
  } catch {
    // ignore errors on logout
  }
  revalidatePath(`/${locale}`);
}

export async function uploadAction(
  _prevState: UploadState,
  formData: FormData,
): Promise<UploadState> {
  const file = formData.get("file");
  if (!(file instanceof Blob) || file.size === 0) {
    return { status: "error", code: "missing_file" };
  }
  try {
    const job = await serverCreateJob(formData);
    return { status: "success", code: "queued", job };
  } catch (error) {
    return {
      status: "error",
      code: "backend",
      message: (error as Error).message || "Upload failed",
    };
  }
}
