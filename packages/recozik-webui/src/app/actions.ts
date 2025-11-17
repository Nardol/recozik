"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { serverFetchWhoami } from "../lib/server/whoami";
import { serverCreateJob } from "../lib/server/jobs";
import type { JobDetail } from "../lib/api";

const TOKEN_COOKIE = "recozik_token";
const SECURE = process.env.NODE_ENV === "production";

export type LoginState = {
  status: "idle" | "error" | "success";
  message: string;
};

const DEFAULT_STATE: LoginState = { status: "idle", message: "" };

export async function loginAction(
  _prevState: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const rawToken = formData.get("token");
  const locale = (formData.get("locale") || "en").toString();
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

export { DEFAULT_STATE };

type UploadState = {
  status: "idle" | "error" | "success";
  code?: "queued" | "missing_token" | "missing_file" | "backend";
  message?: string;
  job?: JobDetail | null;
};

export const DEFAULT_UPLOAD_STATE: UploadState = {
  status: "idle",
  code: undefined,
  message: "",
  job: null,
};

export async function uploadAction(
  _prevState: UploadState,
  formData: FormData,
): Promise<UploadState> {
  const cookieStore = await cookies();
  const token = cookieStore.get(TOKEN_COOKIE)?.value;
  const locale = (formData.get("locale") || "en").toString();
  if (!token) {
    return { status: "error", code: "missing_token" };
  }
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { status: "error", code: "missing_file" };
  }
  try {
    const job = await serverCreateJob(token, formData);
    revalidatePath(`/${locale}`);
    return { status: "success", code: "queued", job };
  } catch (error) {
    return {
      status: "error",
      code: "backend",
      message: (error as Error).message || "Upload failed",
    };
  }
}
