import { test, expect } from "@playwright/test";

// Roles & Access page (feature 016). Auth-gated; admin-only via page:roles.

test("unauthenticated roles page redirects to login", async ({ page }) => {
  await page.goto("/settings/roles");
  await expect(page).toHaveURL(/\/login$/);
});

const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("roles & access page", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
    await page.waitForURL(/\/companies$/);
  }

  test("admin sees the role matrix with seeded roles", async ({ page }) => {
    await login(page);
    await page.goto("/settings/roles");

    await expect(page.getByRole("heading", { name: "Роли и доступ" })).toBeVisible();
    // seeded roles appear as matrix columns
    await expect(page.getByText("Администратор")).toBeVisible();
    await expect(page.getByText("Колл-центр")).toBeVisible();
    await expect(page.getByText("Менеджер")).toBeVisible();
    // permission group headers
    await expect(page.getByText("Страницы")).toBeVisible();
    await expect(page.getByText("Действия")).toBeVisible();
  });

  test("admin can create a new role", async ({ page }) => {
    await login(page);
    await page.goto("/settings/roles");

    const name = `E2E-роль ${Date.now()}`;
    await page.getByTestId("new-role-name").fill(name);
    await page.getByTestId("create-role").click();

    await expect(page.getByText(name)).toBeVisible();
  });
});
