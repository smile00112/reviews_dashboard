import { test, expect } from "@playwright/test";

// Feature 008: the panel is auth-gated. Middleware redirects unauthenticated
// visitors to /login. These smokes need no seeded data.

test("unauthenticated dashboard route redirects to login", async ({ page }) => {
  await page.goto("/companies");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible();
});

test("login form renders email and password fields", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByPlaceholder("admin@example.com")).toBeVisible();
  await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
});

// Full flow (login → create company → add branch). Runs only when admin creds
// are provided, so CI without a seeded user does not fail. Requires API + web +
// Postgres and a seeded admin user.
const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("admin management flow", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  test("login, create company, add branch", async ({ page }) => {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(page.getByRole("heading", { name: "Организации" })).toBeVisible();

    const companyName = `E2E Co ${Date.now()}`;
    await page.getByPlaceholder("Например, Coffee Co").fill(companyName);
    await page.getByRole("button", { name: "+ Организация" }).click();

    await page.getByRole("link", { name: companyName }).click();
    await page.getByRole("button", { name: "+ Филиал" }).click();

    await page.getByPlaceholder("Москва").fill("Москва");
    await page.getByPlaceholder("https://yandex.ru/maps/org/...").fill(
      `https://yandex.ru/maps/org/e2e/${Date.now()}/`,
    );
    await page.getByRole("button", { name: "Создать филиал" }).click();

    await expect(page.getByText("📍 Москва")).toBeVisible();
  });
});
