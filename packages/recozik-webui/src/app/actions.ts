"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { serverCreateJob } from "../lib/server/jobs";
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
    return { status: "error", message: "Missing credentials" };
  }

  const res = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, remember }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "Invalid credentials");
    return { status: "error", message: detail || "Invalid credentials" };
  }

  revalidatePath(`/${locale}`);
  return { status: "success", message: "Logged in" };
}

export async function logoutAction(formData: FormData) {
  const locale = (formData.get("locale") || "en").toString();
  await fetch("/auth/logout", { method: "POST" });
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
