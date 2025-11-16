import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { TokenProvider } from "../components/TokenProvider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Recozik Web Console",
  description: "Accessible dashboard for Recozik identify services",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <a className="visually-hidden" href="#main-content">
          Skip to content
        </a>
        <TokenProvider>
          <div id="main-content">{children}</div>
        </TokenProvider>
      </body>
    </html>
  );
}
