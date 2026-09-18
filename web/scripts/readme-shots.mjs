// Captures the README screenshots against a running stack: node scripts/readme-shots.mjs <doc-id> <eval-ids>
import { chromium } from "@playwright/test";

const [docId, evalIds] = process.argv.slice(2);
const base = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});

await page.goto(`${base}/documents/${docId}`);
await page.getByText("succeeded", { exact: true }).first().waitFor();
await page.locator("li", { hasText: "total" }).last().getByRole("button").first().click();
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(600);
await page.screenshot({ path: "../docs/images/review.png" });

await page.goto(`${base}/evals/compare?ids=${evalIds}`);
await page.getByText("Field accuracy (strict)").waitFor();
await page.waitForTimeout(400);
await page.screenshot({ path: "../docs/images/compare.png" });
await browser.close();
console.log("wrote docs/images/review.png and compare.png");
