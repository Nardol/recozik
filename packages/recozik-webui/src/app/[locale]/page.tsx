import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { DashboardClient } from "../../components/DashboardClient";
import { Providers } from "../../components/Providers";
import { isSupportedLocale } from "../../lib/constants";
import { messages, type Locale } from "../../i18n/messages";

interface Props {
  params: Promise<{ locale: string }>;
}

export default async function LocaleDashboard({ params }: Props) {
  const resolved = await params;
  if (!isSupportedLocale(resolved.locale)) {
    notFound();
  }
  const locale = resolved.locale as Locale;
  const title = messages[locale]["app.title"];
  const cookieStore = await cookies();
  const sessionId = cookieStore.get("recozik_session")?.value ?? null;
  return (
    <>
      <header style={{ position: "absolute", left: "-9999px" }}>
        <h1 data-testid="main-heading">{title}</h1>
      </header>
      <Providers
        locale={resolved.locale}
        initialToken={sessionId}
        initialProfile={null}
      >
        <DashboardClient />
      </Providers>
    </>
  );
}
