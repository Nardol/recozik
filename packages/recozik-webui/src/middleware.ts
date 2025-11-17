import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { isSupportedLocale } from "./lib/constants";

function detectLocale(header: string | null): string {
  if (!header) return "en";
  for (const token of header.split(",")) {
    const [lang] = token.trim().split(";");
    const base = lang?.split("-")[0];
    if (base && isSupportedLocale(base)) {
      return base;
    }
  }
  return "en";
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const segments = pathname.split("/").filter(Boolean);
  const first = segments[0];
  if (!first) {
    const locale = detectLocale(request.headers.get("accept-language"));
    const url = request.nextUrl.clone();
    url.pathname = `/${locale}`;
    return NextResponse.redirect(url);
  }
  if (!isSupportedLocale(first)) {
    return NextResponse.redirect(new URL(`/en${pathname}`, request.url));
  }
  const response = NextResponse.next();
  response.cookies.set("recozik_locale", first, {
    path: "/",
    sameSite: "lax",
  });
  return response;
}

export const config = {
  matcher: ["/:path*"],
};
