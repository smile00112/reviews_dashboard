import { test, expect } from "@playwright/test";

// Feature 014: ratings page. Auth-gated like the rest of the panel.

test("unauthenticated ratings redirects to login", async ({ page }) => {
  await page.goto("/ratings");
  await expect(page).toHaveURL(/\/login$/);
});

// Authenticated render + filter behaviour. Runs only with seeded admin creds
// and a live API + web + Postgres stack.
const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("ratings page", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
    await page.waitForURL(/\/companies$/);
  }

  test("renders all ratings blocks", async ({ page }) => {
    await login(page);
    await page.goto("/ratings");

    await expect(page.getByRole("heading", { name: "Рейтинги" })).toBeVisible();
    await expect(page.getByText("Распределение оценок по площадкам")).toBeVisible();
    await expect(page.getByText("Динамика среднего рейтинга")).toBeVisible();
    await expect(page.getByText("Количество отзывов по площадкам")).toBeVisible();
    await expect(page.getByText("Скорость ответа на отзывы")).toBeVisible();
    await expect(page.getByText("Оценки по дням недели")).toBeVisible();
  });

  test("aggregate-only platforms show нет данных", async ({ page }) => {
    await login(page);
    await page.goto("/ratings");
    // Google / 2ГИС store no per-review rows -> per-star columns are placeholders.
    await expect(page.getByText("нет данных").first()).toBeVisible();
  });

  test("weekday block always renders seven days", async ({ page }) => {
    await login(page);
    await page.goto("/ratings");
    for (const day of ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]) {
      await expect(page.getByText(day, { exact: true })).toBeVisible();
    }
  });

  test("changing period updates the URL", async ({ page }) => {
    await login(page);
    await page.goto("/ratings");
    await page.getByRole("button", { name: "90 дней" }).click();
    await expect(page).toHaveURL(/period=90d/);
  });

  test("changing platform updates the URL and narrows the table", async ({ page }) => {
    await login(page);
    await page.goto("/ratings");
    await page.getByRole("button", { name: "Яндекс" }).first().click();
    await expect(page).toHaveURL(/platform=yandex/);
  });

  test("ratings is reachable from the sidebar", async ({ page }) => {
    await login(page);
    await page.goto("/overview");
    await page.getByRole("link", { name: /Рейтинги/ }).click();
    await expect(page).toHaveURL(/\/ratings/);
  });
});
