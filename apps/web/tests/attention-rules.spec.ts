import { test, expect } from "@playwright/test";

// Attention rules management page. Auth-gated like the rest of the panel.

test("unauthenticated attention-rules redirects to login", async ({ page }) => {
  await page.goto("/attention-rules");
  await expect(page).toHaveURL(/\/login$/);
});

const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("attention rules page", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
    await page.waitForURL(/\/companies$/);
  }

  test("renders the seeded rules list", async ({ page }) => {
    await login(page);
    await page.goto("/attention-rules");
    await expect(page.getByRole("heading", { name: "Правила внимания" })).toBeVisible();
    // Page fetches rules async on mount — wait for the first row before counting.
    await expect(page.getByTestId("rule-row").first()).toBeVisible();
    // 5 сид-правил из миграции 0015 (или больше, если оператор создавал свои).
    expect(await page.getByTestId("rule-row").count()).toBeGreaterThanOrEqual(5);
  });

  test("creates a rule and toggles it", async ({ page }) => {
    await login(page);
    await page.goto("/attention-rules");
    // Page fetches rules async on mount — wait for the first row before counting.
    await expect(page.getByTestId("rule-row").first()).toBeVisible();
    const before = await page.getByTestId("rule-row").count();

    await page.getByTestId("rule-create").click();
    await page.getByTestId("rule-name").fill("e2e-правило");
    await page.getByTestId("param-hours").fill("36");
    await page.getByTestId("rule-submit").click();

    await expect(page.getByText("e2e-правило")).toBeVisible();
    await expect(page.getByTestId("rule-row")).toHaveCount(before + 1);

    const row = page.getByTestId("rule-row").filter({ hasText: "e2e-правило" });
    // Plain click (not .uncheck()): the app's onChange handler calls setPageError(null)
    // synchronously before awaiting the PATCH, which re-renders the controlled checkbox
    // back to its old "checked" value for a tick — .uncheck()'s own post-click verification
    // isn't retry-friendly and trips on that flicker. The auto-retrying expect below polls
    // until the async update (and refresh()) actually lands.
    await row.getByTestId("rule-toggle").click();
    await expect(row.getByTestId("rule-toggle")).not.toBeChecked();

    // Cleanup: удалить созданное правило, чтобы прогон был идемпотентным.
    page.once("dialog", (dialog) => dialog.accept());
    await row.getByRole("button", { name: "Удалить" }).click();
    await expect(page.getByText("e2e-правило")).toHaveCount(0);
    await expect(page.getByTestId("rule-row")).toHaveCount(before);
  });

  test("gear link on overview leads here", async ({ page }) => {
    await login(page);
    await page.goto("/overview");
    await page.getByRole("link", { name: "Настроить правила" }).click();
    await expect(page).toHaveURL(/\/attention-rules$/);
  });
});
