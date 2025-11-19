import type { Metadata } from "next";
import "./globals.css";
import { cookies } from "next/headers";
import { isSupportedLocale } from "../lib/constants";

export const metadata: Metadata = {
  title: "Recozik Web Console",
  description: "Accessible dashboard for Recozik identify services",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const rawLocale = cookieStore.get("recozik_locale")?.value ?? "en";
  const localeCookie = isSupportedLocale(rawLocale) ? rawLocale : "en";
  return (
    <html lang={localeCookie}>
      <body>{children}</body>
    </html>
  );
}
