import { test, expect } from "@playwright/test";

// Reviews page rebuild (GeoMonitor prototype). Auth-gated like the rest of the panel.

test("unauthenticated reviews redirects to login", async ({ page }) => {
  await page.goto("/reviews");
  await expect(page).toHaveURL(/\/login$/);
});

const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("reviews page", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
  }

  test("renders tabs, filters and aspects panel", async ({ page }) => {
    await login(page);
    await page.goto("/reviews");

    await expect(page.getByRole("heading", { name: "Отзывы" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Не отвечено/ })).toBeVisible();
    await expect(page.getByText("Аспектный анализ")).toBeVisible();
    await expect(page.getByText("Лента отзывов")).toBeVisible();
  });

  test("status tab updates the URL", async ({ page }) => {
    await login(page);
    await page.goto("/reviews");
    await page.getByRole("button", { name: /Не отвечено/ }).click();
    await expect(page).toHaveURL(/status=unanswered/);
  });

  test("period chip updates the URL", async ({ page }) => {
    await login(page);
    await page.goto("/reviews");
    await page.getByRole("button", { name: "7д", exact: true }).click();
    await expect(page).toHaveURL(/period=7d/);
  });

  test("escalated deep link opens pre-filtered", async ({ page }) => {
    await login(page);
    await page.goto("/reviews?status=escalated");
    await expect(page.getByRole("button", { name: /Эскалированные/ })).toHaveClass(/border-accent/);
  });
});
