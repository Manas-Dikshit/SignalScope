import type { Metadata } from "next";
import { Inter, Space_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SignalScope AI",
  description: "Explainable RF signal analysis workbench",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable} ${jetbrains.variable}`}>
      <body className="min-h-screen antialiased font-sans">
        <div className="app-background" aria-hidden="true">
          <video
            className="app-background-video"
            autoPlay
            loop
            muted
            playsInline
            preload="metadata"
          >
            <source src="/signalscope-background.mp4" type="video/mp4" />
          </video>
          <div className="app-background-overlay" />
        </div>
        <div className="relative z-10 min-h-screen">
          <Providers>{children}</Providers>
        </div>
      </body>
    </html>
  );
}
