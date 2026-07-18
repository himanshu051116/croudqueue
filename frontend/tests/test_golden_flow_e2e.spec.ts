import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("completes the Gate C blocked, repaired, approved, and published flow", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: "A message can be right for one fan. And wrong for the crowd.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Aurora Stadium" })).toBeVisible();
  await expect(page.getByTestId("venue-node-node-gate-d")).toBeVisible();

  const candidate = page.getByRole("button", {
    name: /Redirect West Flow to Gate A/i,
  });
  await expect(candidate).toBeEnabled();
  await candidate.click();

  const drift = page.getByRole("checkbox", { name: /Simulate semantic drift/i });
  await expect(drift).toBeEnabled();
  await drift.check();
  await page.getByRole("button", { name: /Generate & verify guidance/i }).click();

  await expect(page.getByText("Semantic preflight blocked")).toBeVisible();
  await expect(page.getByText("PROTECTED_COHORT_OMITTED")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve evidence bundle/i })).toHaveCount(0);

  await page.getByRole("button", { name: /Execute targeted repair/i }).click();
  await expect(page.getByText("Semantic verification passed")).toBeVisible();
  await expect(page.getByText(/Español · Fan App/i)).toBeVisible();
  await expect(page.getByText("v2", { exact: true })).toBeVisible();

  await page
    .getByRole("button", { name: /Run 200-sample paired simulation/i })
    .click();
  await expect(page.getByText("Simulation verdict: PASS")).toBeVisible();

  await page.getByRole("button", { name: /Approve evidence bundle/i }).click();
  await expect(page.getByText("Decision bundle approved")).toBeVisible();

  await page.getByRole("button", { name: /Simulate live publication/i }).click();
  await expect(
    page.getByText("Guidance published — simulated recipient surfaces"),
  ).toBeVisible();
  await expect(page.getByText("Fan App (EN/ES/FR)")).toBeVisible();
  await expect(page.getByText("Public Address (EN/ES/FR)")).toBeVisible();
  await expect(page.getByText("Digital Signage (derived)")).toBeVisible();
  await expect(page.getByText("Volunteer Devices (derived)")).toBeVisible();
  await expect(page.getByText("3/3 persisted deliveries complete").first()).toBeVisible();

  await page.reload();
  await expect(
    page.getByText("Guidance published — simulated recipient surfaces"),
  ).toBeVisible();
  await expect(page.getByText("1/1 persisted deliveries complete")).toBeVisible();

  await expect(page.getByText("Hash chain valid")).toBeVisible();
  await expect(page.getByText("PUBLICATION COMPLETED")).toBeVisible();
});

test("exposes accessible scenario controls and a meaningful venue text alternative", async ({ page }) => {
  await page.goto("/");
  const liftScenario = page.getByRole("button", { name: /Lift D2 Concourse Outage/i });
  await expect(liftScenario).toBeEnabled();
  for (let step = 0; step < 10 && !(await liftScenario.evaluate((element) => element === document.activeElement)); step += 1) {
    await page.keyboard.press("Tab");
  }
  await expect(liftScenario).toBeFocused();
  const hasVisibleFocus = await liftScenario.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return style.outlineStyle !== "none" || style.boxShadow !== "none";
  });
  expect(hasVisibleFocus).toBe(true);
  await page.keyboard.press("Enter");

  await page.getByText("Text alternative for the venue map").click();
  const alternative = page.getByTestId("venue-text-alternative");
  await expect(alternative).toContainText("Lift D2 is unavailable");
  await expect(alternative).toContainText("protected accessible route");

  const results = await new AxeBuilder({ page }).analyze();
  const seriousOrCritical = results.violations.filter((violation) =>
    ["serious", "critical"].includes(violation.impact ?? ""),
  );
  expect(seriousOrCritical).toEqual([]);
});

for (const width of [360, 390]) {
  test(`has no document-level horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Aurora Stadium" })).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
  });
}
