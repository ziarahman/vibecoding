import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "IPO Signal Intelligence",
  description:
    "Multi-agent AI pipeline that monitors the internet for IPO financial signals and separates verified facts from speculative noise.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${inter.variable} ${mono.variable} font-sans`}>
        <div className="min-h-screen bg-background">
          <div className="pointer-events-none fixed inset-0 -z-10 bg-grid opacity-[0.35]" />
          {children}
        </div>
      </body>
    </html>
  );
}
