import { expect, test } from "@playwright/test";

// Feature: background jobs (/jobs + /jobs/runs/[id]). Auth-gated like the
// rest of the panel; the manual-run test hits an admin-only endpoint
// (POST /api/jobs/{id}/run), so every test below logs in first.

test("unauthenticated jobs page redirects to login", async ({ page }) => {
  await page.goto("/jobs");
  await expect(page).toHaveURL(/\/login$/);
});

const adminEmail = process.env.E2E_ADMIN_EMAIL;
const adminPassword = process.env.E2E_ADMIN_PASSWORD;

test.describe("Фоновые задачи", () => {
  test.skip(!adminEmail || !adminPassword, "set E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD to run");
  // Serial: "ручной запуск" creates the job-run row that "деталь запуска
  // открывается" depends on. The four seeded jobs are disabled by default and
  // have never run, so on a fresh database the runs table starts empty and
  // the "подробнее" link does not exist yet — with fullyParallel workers the
  // two tests could race on which one creates that row first.
  test.describe.configure({ mode: "serial" });

  async function login(page: import("@playwright/test").Page) {
    await page.goto("/login");
    await page.getByPlaceholder("admin@example.com").fill(adminEmail!);
    await page.getByPlaceholder("••••••••").fill(adminPassword!);
    await page.getByRole("button", { name: "Войти" }).click();
    // The form does a client-side fetch(login) then router.replace("/companies")
    // (see app/login/page.tsx) — there's no browser-level navigation for
    // Playwright's click() to auto-wait on, so a goto() right after click()
    // can race the in-flight POST /api/auth/login and cancel it before the
    // session cookie is set. Wait for the post-login redirect to land first.
    await page.waitForURL(/\/companies$/);
  }

  test("страница показывает четыре задачи", async ({ page }) => {
    await login(page);
    await page.goto("/jobs");
    await expect(page.getByRole("heading", { name: "Фоновые задачи" })).toBeVisible();
    await expect(page.getByTestId("job-card")).toHaveCount(4);
  });

  test("фильтр запусков доступен и не роняет страницу", async ({ page }) => {
    await login(page);
    await page.goto("/jobs");
    await page.getByTestId("status-filter").selectOption("failed");
    await expect(page.getByRole("heading", { name: "Запуски" })).toBeVisible();
  });

  test("ручной запуск создаёт строку в таблице запусков", async ({ page }) => {
    // ОПАСНО на живой базе: клик стартует НАСТОЯЩИЙ фоновый сбор по всем
    // организациям с URL этой площадки (на дев-базе с сотнями организаций это
    // многоминутный реальный скрапинг Яндекса). Поэтому тест выполняется
    // только при явном опте-ине — на чистой тестовой базе (CI/compose).
    test.skip(
      process.env.E2E_ALLOW_JOB_RUN !== "1",
      "set E2E_ALLOW_JOB_RUN=1 to run (starts a REAL scrape of every org in the DB)",
    );
    await login(page);
    await page.goto("/jobs");
    const runButton = page.getByTestId("job-run-now").first();
    await runButton.click();
    await expect(page.getByTestId("job-run-row").first()).toBeVisible({ timeout: 15000 });
  });

  test("деталь запуска открывается", async ({ page }) => {
    await login(page);

    // The runs table starts empty (useState([])) and the "use client" page
    // has no server-fetched data, so its SSR shell already renders
    // "Запусков пока нет." before hydration — that text is transiently
    // visible even when runs exist, so waiting for "a row OR that message"
    // is not a valid empty-check (it resolves the instant the stale SSR
    // text paints, before the real fetch response replaces it). Decide
    // empty-vs-not straight from the intercepted API response body instead
    // of inferring it from DOM timing.
    const runsLoaded = page.waitForResponse(
      (resp) => resp.url().includes("/api/job-runs?") && resp.request().method() === "GET",
    );
    await page.goto("/jobs");
    const resp = await runsLoaded;
    const { items } = (await resp.json()) as { items: unknown[] };

    // Honest precondition check: only the previous test (or an earlier run
    // against a shared dev DB) puts a row in the table. If none exists yet,
    // skip explicitly instead of silently passing on an empty page.
    test.skip(items.length === 0, "нет ни одного запуска задачи — сначала должен пройти ручной запуск");

    // Now that a run is confirmed to exist, wait (auto-retrying) for React
    // to actually paint it before interacting with the link.
    const link = page.getByRole("link", { name: "подробнее" }).first();
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.getByRole("link", { name: "← к задачам" })).toBeVisible();
  });
});
