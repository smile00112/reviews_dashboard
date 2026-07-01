import Link from "next/link";
import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Yandex Reviews Dashboard",
  description: "Internal dashboard for Yandex Maps reviews",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <header className="border-b bg-white">
          <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3 text-sm font-medium">
            <Link href="/organizations" className="font-semibold text-slate-900">
              Yandex Reviews
            </Link>
            <Link href="/organizations" className="text-slate-600 hover:text-slate-900">
              Организации
            </Link>
            <Link href="/reviews" className="text-slate-600 hover:text-slate-900">
              Все отзывы
            </Link>
            <Link href="/scrape-runs" className="text-slate-600 hover:text-slate-900">
              История сборов
            </Link>
            <Link href="/http-scraper" className="text-slate-600 hover:text-slate-900">
              HTTP-парсер
            </Link>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
