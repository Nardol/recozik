import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { isSupportedLocale } from "../lib/constants";

// Force dynamic rendering so Accept-Language is evaluated per request (used by E2E locale tests).
export const dynamic = "force-dynamic";

function detectLocale(header: string | null): string {
  if (!header) return "en";
  const candidates = header.split(",").map((token) => token.trim());
  for (const candidate of candidates) {
    const [lang] = candidate.split(";");
    const base = lang?.split("-")[0];
    if (base && isSupportedLocale(base)) {
      return base;
    }
  }
  return "en";
}

export default async function RootRedirect() {
  const accept = (await headers()).get("accept-language");
  const locale = detectLocale(accept);
  redirect(`/${locale}`);
}
