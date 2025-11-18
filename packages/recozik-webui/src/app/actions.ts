"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { serverFetchWhoami } from "../lib/server/whoami";
import { serverCreateJob } from "../lib/server/jobs";
import type { LoginState, UploadState } from "./action-types";

const TOKEN_COOKIE = "recozik_token";
const SECURE = process.env.NODE_ENV === "production";

export async function loginAction(
  _prevState: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const rawToken = formData.get("token");
  const locale = (formData.get("locale") || "en").toString();
  const shouldPersist = formData.get("remember") === "on";
  const token = (rawToken ?? "").toString().trim();
  if (!token) {
    return { status: "error", message: "Token is required" };
  }
  try {
    await serverFetchWhoami(token);
  } catch (error) {
    return {
      status: "error",
      message: (error as Error).message || "Invalid token",
    };
  }
  const cookieStore = await cookies();
  cookieStore.set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: SECURE,
    path: "/",
    maxAge: shouldPersist ? 60 * 60 * 24 * 30 : undefined,
  });
  revalidatePath(`/${locale}`);
  return { status: "success", message: "Token saved" };
}

export async function logoutAction(formData: FormData) {
  const locale = (formData.get("locale") || "en").toString();
  const cookieStore = await cookies();
  cookieStore.delete(TOKEN_COOKIE);
  revalidatePath(`/${locale}`);
}

export async function uploadAction(
  _prevState: UploadState,
  formData: FormData,
): Promise<UploadState> {
  const cookieStore = await cookies();
  const token = cookieStore.get(TOKEN_COOKIE)?.value;
  if (!token) {
    return { status: "error", code: "missing_token" };
  }
  const file = formData.get("file");
  if (!(file instanceof Blob) || file.size === 0) {
    return { status: "error", code: "missing_file" };
  }
  try {
    const job = await serverCreateJob(token, formData);
    return { status: "success", code: "queued", job };
  } catch (error) {
    return {
      status: "error",
      code: "backend",
      message: (error as Error).message || "Upload failed",
    };
  }
}
