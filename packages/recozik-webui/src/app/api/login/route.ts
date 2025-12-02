import { NextRequest, NextResponse } from "next/server";

function resolveApiBase(): string {
  const preferred = process.env.RECOZIK_WEB_API_BASE?.trim();
  if (preferred) return preferred.replace(/\/$/, "");
  const fallback = process.env.NEXT_PUBLIC_RECOZIK_API_BASE?.trim();
  if (fallback) return fallback.replace(/\/$/, "");
  return "http://backend:8000";
}

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const username = (formData.get("username") || "").toString();
  const password = (formData.get("password") || "").toString();
  const remember = formData.get("remember") === "on";
  const locale = (formData.get("locale") || "en").toString();

  const apiBase = resolveApiBase();
  const backendResponse = await fetch(`${apiBase}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, remember }),
    redirect: "manual",
  });

  const origin = request.nextUrl.origin;
  const successUrl = `${origin}/${locale}`;

  if (!backendResponse.ok) {
    let errorKey = "invalid_credentials";
    try {
      const errorData = await backendResponse.json();
      const detail = errorData?.detail;
      if (detail === "user_disabled") errorKey = "account_disabled";
      else if (detail === "invalid_credentials")
        errorKey = "invalid_credentials";
    } catch {
      // fallback to generic key
      errorKey = "invalid_credentials";
    }
    return NextResponse.redirect(
      `${successUrl}?login_error=${encodeURIComponent(errorKey)}`,
      {
        status: 303,
      },
    );
  }

  const response = NextResponse.redirect(successUrl, { status: 303 });
  const setCookie = backendResponse.headers.getSetCookie();
  setCookie.forEach((cookie) => response.headers.append("set-cookie", cookie));
  return response;
}
