import { headers } from "next/headers";
import { redirect } from "next/navigation";

const SUPPORTED = ["en", "fr"];

function detectLocale(header: string | null): string {
  if (!header) return "en";
  const candidates = header.split(",").map((token) => token.trim());
  for (const candidate of candidates) {
    const [lang] = candidate.split(";");
    const base = lang?.split("-")[0];
    if (base && SUPPORTED.includes(base)) {
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
