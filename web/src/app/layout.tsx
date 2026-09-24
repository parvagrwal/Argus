import type { Metadata } from "next";
import { Space_Grotesk, JetBrains_Mono, Figtree, Fraunces } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

const figtree = Figtree({
  subsets: ["latin"],
  variable: "--font-figtree",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["900"],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Argus — Agentic Fraud Investigation on TigerGraph",
  description: "25 investigations. 590,742 transactions. One graph. Built for Hacker House Goa 2026.",
  icons: {
    icon: "/brand/2-47.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${jetbrainsMono.variable} ${figtree.variable} ${fraunces.variable} dark`}
    >
      <body className="bg-forest text-cream font-sans antialiased selection:bg-[#FF0080] selection:text-white min-h-screen flex flex-col">
        {children}
      </body>
    </html>
  );
}
