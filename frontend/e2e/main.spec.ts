import path from "node:path";
import { expect, test } from "@playwright/test";

const SAMPLE = path.resolve(__dirname, "../../examples/sample-plan.xlsx");

test("demo → import → chat edit → export", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Сбор требований и приоритизация").first()).toBeVisible();

  await page.getByRole("button", { name: "Загрузить Excel" }).click();
  await page.locator('input[type="file"]').setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Загрузить", exact: true }).click();
  await expect(page.getByText("Упаковка мебели").first()).toBeVisible();
  await expect(page.getByText("Сбор требований и приоритизация")).toHaveCount(0);

  await page.getByRole("textbox", { name: /сообщение/i }).fill("Сдвинь все задачи Олега на 3 дня");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Изменено задач: \d+/).first()).toBeVisible({ timeout: 20_000 });

  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Экспорт" }).click();
  expect((await download).suggestedFilename()).toMatch(/^plan-\d{4}-\d{2}-\d{2}\.xlsx$/);

  await page.getByText("Упаковка мебели").first().click();
  await expect(page.getByRole("dialog")).toContainText("Упаковка мебели");
});
