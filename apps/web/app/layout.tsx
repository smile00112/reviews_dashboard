import "./globals.css";
import type { ReactNode } from "react";
import { Fraunces, Manrope, JetBrains_Mono } from "next/font/google";

const manrope = Manrope({ subsets: ["latin", "cyrillic"], variable: "--font-manrope" });
const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata = {
  title: "SERM Dashboard",
  description: "Панель управления сбором отзывов с карт",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" className={`${manrope.variable} ${fraunces.variable} ${jetbrains.variable}`}>
      <body>{children}</body>
    </html>
  );
}
