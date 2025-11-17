import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { DashboardClient } from "../../components/DashboardClient";
import { Providers } from "../../components/Providers";

const SUPPORTED_LOCALES = ["en", "fr"];

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
  return (
    <Providers locale={locale} initialToken={token}>
      <DashboardClient />
    </Providers>
  );
}
