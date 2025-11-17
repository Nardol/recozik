import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { DashboardClient } from "../../components/DashboardClient";
import { Providers } from "../../components/Providers";
import { serverFetchWhoami } from "../../lib/server/whoami";
import { SUPPORTED_LOCALES } from "../../lib/constants";

interface Props {
  params: { locale: string };
}

export default async function LocaleDashboard({ params }: Props) {
  const locale = SUPPORTED_LOCALES.includes(params.locale)
    ? params.locale
    : null;
  if (!locale) {
    notFound();
  }
  const cookieStore = await cookies();
  const token = cookieStore.get("recozik_token")?.value ?? null;
  let profile = null;
  if (token) {
    try {
      profile = await serverFetchWhoami(token);
    } catch (error) {
      console.error("Failed to fetch user profile:", error);
      profile = null;
    }
  }
  return (
    <Providers locale={locale} initialToken={token} initialProfile={profile}>
      <DashboardClient />
    </Providers>
  );
}
