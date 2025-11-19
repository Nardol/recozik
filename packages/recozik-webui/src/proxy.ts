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

export function proxy(request: NextRequest) {
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
    const remainder = segments.slice(1).join("/");
    const nextPath = remainder ? `/en/${remainder}` : "/en";
    return NextResponse.redirect(new URL(nextPath, request.url));
  }
  const response = NextResponse.next();
  response.cookies.set("recozik_locale", first, {
    path: "/",
    sameSite: "lax",
  });
  return response;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
