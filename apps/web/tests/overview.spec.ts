import { test, expect } from "@playwright/test";

// Feature 009: network overview dashboard. Auth-gated like the rest of the panel.

test("unauthenticated overview redirects to login", async ({ page }) => {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login$/);
});

test("root redirects to overview (then to login when unauthenticated)", async ({ page }) => {
  await page.goto("/");
  // Root → /overview → (auth gate) → /login
  await expect(page).toHaveURL(/\/login$/);
});

// Authenticated render + filter behaviour. Runs only with seeded admin creds
// and a live API + web + Postgres stack.
const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("overview page", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
  }

  test("renders all overview blocks", async ({ page }) => {
    await login(page);
    await page.goto("/overview");

    await expect(page.getByRole("heading", { name: "Обзор сети" })).toBeVisible();
    await expect(page.getByText("Средний рейтинг сети")).toBeVisible();
    await expect(page.getByText("Распределение оценок")).toBeVisible();
    await expect(page.getByText("Тональность отзывов")).toBeVisible();
    await expect(page.getByText("Требуют внимания за последние 24 часа")).toBeVisible();
    await expect(page.getByText("Топ-10 худших точек")).toBeVisible();
    // Google card has no per-review data.
    await expect(page.getByText("нет данных").first()).toBeVisible();
  });

  test("changing period updates the URL", async ({ page }) => {
    await login(page);
    await page.goto("/overview");
    await page.getByRole("button", { name: "90 дней" }).click();
    await expect(page).toHaveURL(/period=90d/);
  });

  test("changing platform updates the URL", async ({ page }) => {
    await login(page);
    await page.goto("/overview");
    await page.getByRole("button", { name: "Яндекс", exact: true }).click();
    await expect(page).toHaveURL(/platform=yandex/);
  });
});
