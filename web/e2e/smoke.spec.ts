import path from "node:path";
import { expect, test } from "@playwright/test";

const FIXTURE = path.resolve(
  __dirname,
  "../../backend/tests/fixtures/cord/cord-v2_validation_0006.jpg",
);

test("upload → OCR → extraction → correction, end to end", async ({ page }) => {
  await page.goto("/documents");
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();

  // Upload through the hidden input behind the dropzone button.
  await page.locator('input[type="file"]').setInputFiles(FIXTURE);
  await expect(page).toHaveURL(/\/documents\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name: "cord-v2_validation_0006.jpg" })).toBeVisible();

  // The worker runs OCR (RapidOCR) and the page polls until it is done.
  await expect(page.getByText("done", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole("switch", { name: "OCR boxes" }).click();
  await expect(page.locator("button[title]").first()).toBeVisible();

  // Queue an extraction; with LLM_PROVIDER=fake the worker answers with an all-null result.
  await page.getByRole("button", { name: "Run extraction" }).click();
  await expect(page.getByText("succeeded", { exact: true }).first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("line items", { exact: true }).first()).toBeVisible();

  // Correct the total and save: it becomes the golden label.
  await page.getByRole("button", { name: "Edit values" }).click();
  const totalInput = page.locator("li", { hasText: "total" }).last().getByRole("textbox");
  await totalInput.fill("45500");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText("Correction saved")).toBeVisible();
  await expect(page.getByText("golden: correction")).toBeVisible();

  // The document now shows as labelled in the list.
  await page.goto("/documents?split=upload");
  await expect(
    page.getByRole("row", { name: /cord-v2_validation_0006\.jpg/ }).getByText("labelled"),
  ).toBeVisible();
});

test("eval pages render", async ({ page }) => {
  await page.goto("/evals");
  await expect(page.getByRole("heading", { name: "Evals" })).toBeVisible();
  await page.goto("/schemas");
  await expect(page.getByText("line_items[].line_total")).toBeVisible();
});
