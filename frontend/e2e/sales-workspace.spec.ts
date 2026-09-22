import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const richSalesFixture = fixture("phase7_browser_retail.csv");
const quarantineFixture = fixture("browser_invalid_sales.csv");
const limitedHistoryFixture = fixture("browser_limited_history.csv");
const productDemandFixture = fixture("product_demand_positive_control.csv");
const categoryFallbackFixture = fixture("product_demand_category_fallback.csv");
const retailerDemoFixture = fixture("retailer_demo/retailer_sales.csv");
const retailerPolicyFixture = fixture("retailer_demo/shipping_policy.md");

test("uploads a rich sales CSV and renders evidence-backed intelligence", async ({ page }) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, richSalesFixture, "phase7_browser_retail.csv");

  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page.getByPlaceholder("USD", { exact: true }).fill("NGN");
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();

  const statusSuggestions = page.getByRole("button", {
    name: "Apply common-value suggestions",
  });
  await expect(statusSuggestions).toHaveCount(2);
  await statusSuggestions.nth(0).click();
  await statusSuggestions.nth(1).click();
  await page.getByLabel("Discount representation").selectOption("fixed");
  await page
    .getByLabel("No — refund amount is only the revenue refund")
    .check();

  await page.getByRole("button", { name: "Validate data" }).click();
  await expect(page.getByText("Every row passed validation.")).toBeVisible();
  await page.getByRole("button", { name: "Generate intelligence dashboard" }).click();

  await expect(page.getByRole("heading", { name: "Your Sales Intelligence" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What changed and what to review" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Forecast Evidence" })).toBeVisible();
  await expect(page.getByText("Methods tested")).toBeVisible();
  await expect(
    page.getByText("Actual data ends in 2026-08. Forecast begins the following month."),
  ).toBeVisible();
  await expect(page.getByText("Forecast begins after 2026-08")).toBeVisible();

  const revenueCard = page.locator(".card--wide").filter({ hasText: "Revenue Trend" });
  const revenueChart = revenueCard.locator(".recharts-wrapper");
  await revenueChart.scrollIntoViewIfNeeded();
  const chartBox = await revenueChart.boundingBox();
  if (!chartBox) throw new Error("Revenue chart did not render");
  await page.mouse.move(
    chartBox.x + chartBox.width * 0.865,
    chartBox.y + chartBox.height * 0.5,
  );
  await expect(revenueCard.getByText("Forecast begins next month.")).toBeVisible();
  await expect(revenueCard.locator(".tooltip").getByText("Forecast", { exact: true })).toHaveCount(0);

  await expect(page.getByRole("link", { name: "Download canonical CSV" })).toBeVisible();
  await expect(page.getByText("0 quarantined")).toBeVisible();
});

test("distinguishes loading status values from a real loading failure", async ({ page }) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, richSalesFixture, "phase7_browser_retail.csv");
  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();

  let releaseDistinctValues = () => undefined;
  const distinctValuesGate = new Promise<void>((resolve) => {
    releaseDistinctValues = resolve;
  });
  await page.route("**/api/v1/uploads/distinct-values", async (route) => {
    await distinctValuesGate;
    await route.continue();
  });

  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Loading status values…")).toBeVisible();
  await expect(page.getByText(/Status values could not be loaded/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Validate data" })).toBeDisabled();

  releaseDistinctValues();
  await expect(page.getByText("Loading status values…")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Apply common-value suggestions" })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Validate data" })).toBeEnabled();

  await page.unroute("**/api/v1/uploads/distinct-values");
  await page.route("**/api/v1/uploads/distinct-values", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"unavailable"}' });
  });
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Status values could not be loaded. Data validation remains disabled.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry status values" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Validate data" })).toBeDisabled();
});

test("blocks analysis until invalid rows are explicitly quarantined", async ({ page }) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, quarantineFixture, "browser_invalid_sales.csv");
  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page.getByRole("button", { name: "Validate mapping" }).click();
  const mappingNotice = page.locator(".notice--error");
  await expect(mappingNotice).toContainText("In the Row or order total dropdown, select Total.");
  await expect(mappingNotice.locator("code")).toHaveText("Total");
  await page
    .getByRole("combobox", { name: /Row or order total Required/ })
    .selectOption("Total");
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();
  await page.getByLabel("Confirm every row is a completed sale").check();

  await page.getByRole("button", { name: "Validate data" }).click();
  await expect(page.getByText("Quarantine 1 invalid rows", { exact: true })).toBeVisible();
  await expect(page.getByText("Preview only", { exact: true })).toBeVisible();
  const repairGuide = page.locator(".repair-guide");
  await expect(repairGuide.getByText("How to correct the CSV")).toBeVisible();
  await expect(repairGuide.getByText("Date", { exact: true })).toBeVisible();
  await expect(repairGuide.getByText("Affected location: CSV line 3 (data row 2) · Date column.")).toBeVisible();

  const generateDashboard = page.getByRole("button", {
    name: "Generate intelligence dashboard",
  });
  await expect(generateDashboard).toBeDisabled();
  await page.getByLabel("Quarantine 1 invalid rows").check();
  await expect(generateDashboard).toBeEnabled();
  await generateDashboard.click();

  await expect(page.getByRole("heading", { name: "Your Sales Intelligence" })).toBeVisible();
  await expect(page.getByText("2 valid rows")).toBeVisible();
  await expect(page.getByText("1 quarantined")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Preview Mode — correct the CSV before making decisions" })).toBeVisible();
  await expect(page.getByText(/Forecast was not calculated because this is a preview-only analysis/).first()).toBeVisible();
  await expect(page.getByText(/Diagnostics and recommendations were not calculated because this is a preview-only analysis/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Download quarantine CSV" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download rows to correct" })).toBeVisible();
  await expect(page.getByText("Affected location: CSV line 3 (data row 2) · Date column.").first()).toBeVisible();
});

test("shows honest unavailable states when history or optional fields are missing", async ({
  page,
}) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, limitedHistoryFixture, "browser_limited_history.csv");
  await applySimpleSalesRules(page);

  await page.getByRole("button", { name: "Validate data" }).click();
  await expect(page.getByText("Every row passed validation.")).toBeVisible();
  await page.getByRole("button", { name: "Generate intelligence dashboard" }).click();

  await expect(page.getByRole("heading", { name: "Your Sales Intelligence" })).toBeVisible();
  const forecastEvidence = page.locator(".evidence-card").filter({
    has: page.getByRole("heading", { name: "Forecast Evidence" }),
  });
  await expect(forecastEvidence).toContainText("unavailable trust");
  await expect(forecastEvidence).toContainText("Forecast unavailable");
  await expect(page.getByText("This diagnostic cannot be assessed reliably yet.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Category analysis unavailable" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Regional analysis unavailable" })).toBeVisible();
});

test("evaluates an eligible product-demand preview in the dashboard", async ({ page }) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, productDemandFixture, "product_demand_positive_control.csv");

  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();
  await page.getByRole("button", { name: "Apply common-value suggestions" }).click();
  await page.getByRole("button", { name: "Validate data" }).click();
  await expect(page.getByText("Every row passed validation.")).toBeVisible();
  await page.getByRole("button", { name: "Generate intelligence dashboard" }).click();

  await expect(page.getByRole("heading", { name: "Plan the next seven days by product" })).toBeVisible();
  await page.getByLabel(/The export covers every open business day/).check();
  await page.getByLabel(/There were no unrecorded stockout days/).check();
  await page.getByRole("button", { name: "Evaluate product demand" }).click();

  await expect(page.getByText("Preview forecasts").locator("..").getByText("1")).toBeVisible();
  await expect(page.getByText("7 portion")).toBeVisible();
  await expect(page.getByText("1 portion")).toBeVisible();
  await expect(page.getByText("Average daily planning rate")).toBeVisible();
  await expect(page.getByText(/Preview — not decision-ready/).first()).toBeVisible();
  await expect(page.getByText(/Why this method:/)).toBeVisible();
});

test("clears discount rules when a replacement CSV has no discount column", async ({ page }) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, richSalesFixture, "phase7_browser_retail.csv");
  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();
  await page.getByLabel("Discount representation").selectOption("fixed");

  await page.locator('.preview-card input[type="file"]').setInputFiles(productDemandFixture);
  await expect(page.getByRole("heading", { name: "product_demand_positive_control.csv" })).toBeVisible();
  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();

  const discountRepresentation = page.getByLabel("Discount representation");
  await expect(discountRepresentation).toHaveValue("none");
  await expect(discountRepresentation).toBeDisabled();

  await page.getByRole("button", { name: "Apply common-value suggestions" }).click();
  await page.getByRole("button", { name: "Validate data" }).click();
  await expect(page.getByText("Every row passed validation.")).toBeVisible();
  await expect(page.getByText("The selected discount type requires a mapped discount column.")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Generate intelligence dashboard" })).toBeEnabled();
});

test("shows a category fallback when sparse products are jointly predictable", async ({ page }) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, categoryFallbackFixture, "product_demand_category_fallback.csv");

  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();
  await page.getByRole("button", { name: "Apply common-value suggestions" }).click();
  await page.getByRole("button", { name: "Validate data" }).click();
  await expect(page.getByText("Every row passed validation.")).toBeVisible();
  await page.getByRole("button", { name: "Generate intelligence dashboard" }).click();

  await page.getByLabel(/The export covers every open business day/).check();
  await page.getByLabel(/There were no unrecorded stockout days/).check();
  await page.getByLabel(/The mapped product categories are correct/).check();
  await page.getByRole("button", { name: "Evaluate product demand" }).click();

  await expect(page.getByText("Category fallbacks").locator("..").getByText("1")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Meal Kits" })).toBeVisible();
  await expect(page.getByText("2 products combined")).toBeVisible();
  await expect(page.getByText("7 portion")).toBeVisible();
  await expect(page.getByText(/does not allocate demand to individual products/)).toBeVisible();
});

test("walks a fictional online retailer from sales upload to demand preview and document evidence", async ({ page }) => {
  await openUploadWorkspace(page);
  await uploadFixture(page, retailerDemoFixture, "retailer_sales.csv");
  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();
  await page.getByRole("button", { name: "Apply common-value suggestions" }).click();
  await page.getByRole("button", { name: "Validate data" }).click();
  await expect(page.getByText("Every row passed validation.")).toBeVisible();
  await page.getByRole("button", { name: "Generate intelligence dashboard" }).click();

  await expect(page.getByRole("heading", { name: "Plan the next seven days by product" })).toBeVisible();
  await page.getByLabel(/The export covers every open business day/).check();
  await page.getByLabel(/There were no unrecorded stockout days/).check();
  await page.getByRole("button", { name: "Evaluate product demand" }).click();
  await expect(page.getByText("Preview forecasts").locator("..").getByText("1")).toBeVisible();
  await expect(page.getByText("7 piece")).toBeVisible();
  await expect(page.getByText(/not restocking commitments/)).toBeVisible();

  const panel = page.locator(".evidence-search");
  await expect(panel.getByRole("heading", { name: "Ask approved business documents" })).toBeVisible();
  await panel.locator('input[type="file"]').setInputFiles(retailerPolicyFixture);
  await panel.getByRole("button", { name: "Upload and index" }).click();
  await expect(panel.getByText("1 active latest document")).toBeVisible();

  const question = panel.getByLabel("Ask an English question about the approved documents");
  await question.fill("How long does standard Lagos delivery take?");
  await panel.getByRole("button", { name: "Get grounded answer" }).click();
  await expect(panel.getByRole("heading", { name: "Grounded answer" })).toBeVisible();
  await expect(
    panel.getByRole("paragraph").filter({ hasText: "2 to 4 business days" }),
  ).toBeVisible();
  await panel.getByText("Technical retrieval evidence").click();
  await expect(panel.getByText("Retrieval score")).toBeVisible();

  await page.route("**/rag/answer", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "unavailable",
        analysis_id: "browser-test",
        search_scope: "active_latest_documents_in_anonymous_guest_analysis",
        provider: "unavailable",
        model: "gemini-3.8-flash",
        latency_ms: 1,
        reason_codes: ["answer_provider_unavailable"],
        claims: [],
        evidence: [
          {
            chunk_id: "browser-shipping-chunk",
            document_id: "browser-shipping-document",
            document_version: 1,
            document_type: "policy",
            filename: "shipping.md",
            heading: "Delivery",
            excerpt: "Standard Lagos delivery takes 2 to 4 business days.",
            citation: "shipping.md v1 § Delivery · chunk 1",
            rank: 1,
            untrusted_data: true,
            technical: {
              retrieval_score: 0.9,
              method_scores: {},
              rerank_score: null,
            },
          },
        ],
        technical: {
          selected_method: "tfidf",
          searched_document_count: 1,
          searched_chunk_count: 1,
          retrieval_latency_ms: 1,
        },
      }),
    });
  });
  await question.fill("What is the delivery policy?");
  await panel.getByRole("button", { name: "Get grounded answer" }).click();
  await expect(
    panel.getByRole("heading", { name: "Grounded answer is temporarily unavailable" }),
  ).toBeVisible();
  await expect(panel.getByText("Relevant evidence was found, but Gemini is temporarily unavailable.")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Retry grounded answer" })).toBeVisible();
  await page.unroute("**/rag/answer");

  await question.fill("Which television advertisement caused profit to increase?");
  await panel.getByRole("button", { name: "Get grounded answer" }).click();
  await expect(panel.getByRole("heading", { name: "Insufficient evidence" })).toBeVisible();
  await expect(panel.getByText(/returned no evidence instead of guessing/)).toBeVisible();
});

async function openUploadWorkspace(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: /Upload a sales CSV/ }).click();
  await expect(page.getByRole("heading", { name: "Upload transaction data" })).toBeVisible();
}

async function uploadFixture(page: Page, path: string, filename: string): Promise<void> {
  await page.locator('input[type="file"]').setInputFiles(path);
  await expect(page.getByRole("heading", { name: filename })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply recommendations, then review" }),
  ).toBeVisible();
}

async function applySimpleSalesRules(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Apply recommendations, then review" }).click();
  await page
    .getByRole("combobox", { name: /Row or order total Required/ })
    .selectOption("Total");
  await page.getByRole("button", { name: "Validate mapping" }).click();
  await expect(page.getByText("Mapping is valid")).toBeVisible();
  await page.getByLabel("Confirm every row is a completed sale").check();
}

function fixture(filename: string): string {
  return fileURLToPath(new URL(`../../tests/fixtures/${filename}`, import.meta.url));
}
