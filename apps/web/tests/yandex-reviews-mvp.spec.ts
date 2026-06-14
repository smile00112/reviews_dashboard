import { test, expect } from "@playwright/test";

test("organization board loads", async ({ page }) => {
  await page.goto("/organizations");
  await expect(page.getByRole("heading", { name: "Организации" })).toBeVisible();
  await expect(page.getByLabel("URL организации Яндекс Карт")).toBeVisible();
});

test("navigation links are visible", async ({ page }) => {
  await page.goto("/organizations");
  await expect(page.getByRole("link", { name: "Все отзывы" })).toBeVisible();
  await expect(page.getByRole("link", { name: "История сборов" })).toBeVisible();
});

test("reviews page shows empty state", async ({ page }) => {
  await page.goto("/reviews");
  await expect(page.getByRole("heading", { name: "Все отзывы" })).toBeVisible();
});
