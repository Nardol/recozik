import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { DashboardClient } from "../../components/DashboardClient";
import { Providers } from "../../components/Providers";
import { serverFetchWhoami } from "../../lib/server/whoami";
import { isSupportedLocale } from "../../lib/constants";

interface Props {
  params: Promise<{ locale: string }>;
}

export default async function LocaleDashboard({ params }: Props) {
  const resolved = await params;
  if (!isSupportedLocale(resolved.locale)) {
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
    <Providers
      locale={resolved.locale}
      initialToken={token}
      initialProfile={profile}
    >
      <DashboardClient />
    </Providers>
  );
}
