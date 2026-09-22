import { useEffect, useMemo, useState } from "react";

import {
  analyzeUpload,
  deleteAnalysis,
  deleteUpload,
  fetchDistinctValues,
  fetchMappingSuggestions,
  fetchAnalysis,
  uploadCsv,
  validateData,
  validateMapping,
} from "../api";
import type {
  CsvPreviewResponse,
  DataValidationResponse,
  DiscountScope,
  DiscountType,
  DistinctValuesResponse,
  GenericAnalysisResponse,
  MappingSuggestionsResponse,
  NegativeRevenuePolicy,
  OrderDiscountAllocation,
  RevenueMismatchPolicy,
  RefundTaxTreatment,
  RevenueMode,
  SalesConfiguration,
  SchemaMappingResponse,
  StandardOrderStatus,
  StandardPaymentStatus,
} from "../types";
import { BusinessDashboard } from "./BusinessDashboard";
import { DashboardStatus } from "./DashboardShell";

const DATE_FORMATS = [
  { value: "%Y-%m-%d", label: "2025-12-31 — year, month, day" },
  { value: "%d/%m/%Y", label: "31/12/2025 — day, month, year" },
  { value: "%m/%d/%Y", label: "12/31/2025 — month, day, year" },
  { value: "%d-%m-%Y", label: "31-12-2025 — day, month, year" },
  { value: "%Y-%m-%d %H:%M:%S", label: "2025-12-31 14:30:00 — with time" },
] as const;

const FIELD_LABELS: Record<string, string> = {
  order_id: "Order ID",
  order_date: "Order date",
  customer_id: "Customer ID",
  revenue: "Row or order total",
  unit_price: "Unit price",
  quantity: "Quantity",
  discount: "Discount",
  product_id: "Product / SKU code",
  product_name: "Product name",
  unit_of_measure: "Unit of measure",
  product_category: "Product category",
  state_or_region: "State or region",
  order_status: "Order status",
  payment_status: "Payment status",
  payment_amount: "Payment amount",
  refund_amount: "Refund amount",
  returned_quantity: "Returned quantity",
  recognition_date: "Revenue recognition date",
  refund_date: "Refund date",
  tax_amount: "Tax amount",
  shipping_amount: "Shipping amount",
  chargeback_amount: "Chargeback amount",
  currency: "Row currency",
  line_item_id: "Line item ID",
};

const ALIASES: Record<string, string[]> = {
  order_id: ["orderid", "ordernumber", "invoice", "invoiceid", "transactionid"],
  order_date: ["orderdate", "transactiondate", "date", "saledate", "purchasedate", "invoicedate", "timestamp"],
  customer_id: ["customerid", "customercode", "customer", "clientid", "clientcode", "client", "buyerid"],
  revenue: ["revenue", "total", "amount", "sales", "ordertotal", "totalamount"],
  unit_price: ["unitprice", "sellingprice", "saleprice", "price", "itemprice"],
  quantity: ["quantity", "qty", "units", "unitssold"],
  discount: ["discount", "discountamount", "discountvalue", "couponamount"],
  product_id: ["productid", "productcode", "stockcode", "skucode", "sku", "itemcode"],
  product_name: ["productname", "itemname", "stockdescription", "description"],
  unit_of_measure: ["unitofmeasure", "uom", "quantityunit", "salesunit", "unit"],
  product_category: ["productcategory", "merchandisedepartment", "category", "department"],
  state_or_region: ["stateorregion", "salesterritory", "territory", "state", "region", "province", "location", "city"],
  order_status: ["orderstatus", "status", "fulfillmentstatus"],
  payment_status: ["paymentstatus", "transactionstatus", "paymentstate"],
  payment_amount: ["paymentamount", "amountpaid", "collectedamount"],
  refund_amount: ["refundamount", "refundedamount", "refund"],
  returned_quantity: ["returnedquantity", "returnquantity", "qtyreturned"],
  recognition_date: ["recognitiondate", "completeddate", "paiddate"],
  refund_date: ["refunddate", "returneddate"],
  tax_amount: ["taxamount", "tax", "vat", "vatamount"],
  shipping_amount: ["shippingamount", "shipping", "deliveryfee", "freightvalue"],
  chargeback_amount: ["chargebackamount", "disputeamount"],
  currency: ["currency", "currencycode", "iso4217"],
  line_item_id: ["lineitemid", "orderitemid", "itemid"],
};

const ORDER_STATUSES: Array<{ value: StandardOrderStatus; label: string }> = [
  { value: "completed", label: "Completed — recognized sale" },
  { value: "pending", label: "Pending — show separately" },
  { value: "cancelled", label: "Cancelled — exclude" },
  { value: "returned", label: "Returned — record sale and refund" },
];

const PAYMENT_STATUSES: Array<{ value: StandardPaymentStatus; label: string }> = [
  { value: "paid", label: "Paid" },
  { value: "refunded", label: "Refunded" },
  { value: "pending", label: "Pending" },
  { value: "failed", label: "Failed" },
  { value: "voided", label: "Voided" },
  { value: "disputed", label: "Disputed" },
  { value: "chargeback_won", label: "Chargeback won" },
  { value: "chargeback_lost", label: "Chargeback lost" },
];

interface BusinessWorkspaceProps {
  onBack: () => void;
}

type DistinctValuesLoadState = "idle" | "loading" | "ready" | "error";

export function BusinessWorkspace({ onBack }: BusinessWorkspaceProps) {
  const [savedAnalysisId] = useState(() => sessionStorage.getItem("sales-analysis-id"));
  const [restoring, setRestoring] = useState(Boolean(savedAnalysisId));
  const [analysis, setAnalysis] = useState<GenericAnalysisResponse | null>(null);
  const [preview, setPreview] = useState<CsvPreviewResponse | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [revenueMode, setRevenueMode] = useState<RevenueMode>("row_total");
  const [negativePolicy, setNegativePolicy] = useState<NegativeRevenuePolicy>("invalid");
  const [dateFormat, setDateFormat] = useState("%Y-%m-%d");
  const [currency, setCurrency] = useState("USD");
  const [latestPeriodComplete, setLatestPeriodComplete] = useState(true);
  const [assumeAllCompleted, setAssumeAllCompleted] = useState(false);
  const [statusMapping, setStatusMapping] = useState<Record<string, StandardOrderStatus>>({});
  const [paymentStatusMapping, setPaymentStatusMapping] = useState<
    Record<string, StandardPaymentStatus>
  >({});
  const [distinctValues, setDistinctValues] = useState<DistinctValuesResponse | null>(null);
  const [distinctValuesLoadState, setDistinctValuesLoadState] =
    useState<DistinctValuesLoadState>("idle");
  const [mappingSuggestions, setMappingSuggestions] = useState<MappingSuggestionsResponse | null>(null);
  const [discountType, setDiscountType] = useState<DiscountType>("none");
  const [discountScope, setDiscountScope] = useState<DiscountScope>("per_line");
  const [orderDiscountAllocation, setOrderDiscountAllocation] =
    useState<OrderDiscountAllocation>("unallocated");
  const [mismatchPolicy, setMismatchPolicy] = useState<RevenueMismatchPolicy>("warn");
  const [mismatchTolerance, setMismatchTolerance] = useState(0.01);
  const [refundTaxTreatment, setRefundTaxTreatment] = useState<RefundTaxTreatment | null>(null);
  const [mappingResult, setMappingResult] = useState<SchemaMappingResponse | null>(null);
  const [validation, setValidation] = useState<DataValidationResponse | null>(null);
  const [quarantineConfirmed, setQuarantineConfirmed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!savedAnalysisId) return;
    let active = true;
    fetchAnalysis(savedAnalysisId)
      .then((result) => {
        if (active) setAnalysis(result);
      })
      .catch(() => {
        sessionStorage.removeItem("sales-analysis-id");
        if (active) setError("Your previous analysis session expired. Upload the CSV again to continue.");
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
  }, [savedAnalysisId]);

  const activeFields = useMemo(() => fieldsForMode(revenueMode), [revenueMode]);
  const dateFormatHint = useMemo(
    () => suggestDateFormat(preview, mapping.order_date),
    [preview, mapping.order_date],
  );
  const effectiveDiscountType: DiscountType = mapping.discount ? discountType : "none";
  const statusColumns = [mapping.order_status, mapping.payment_status].filter(
    (column): column is string => Boolean(column),
  );
  const statusValuesRequired = statusColumns.length > 0;
  const statusValuesReady = !statusValuesRequired || distinctValuesLoadState === "ready";
  const configuration: SalesConfiguration | null = preview
    ? {
        upload_id: preview.upload_id,
        mapping,
        revenue_mode: revenueMode,
        negative_revenue_policy: negativePolicy,
        date_format: dateFormat,
        currency,
        assume_all_completed: mapping.order_status ? false : assumeAllCompleted,
        status_mapping: statusMapping,
        payment_status_mapping: paymentStatusMapping,
        discount_type: effectiveDiscountType,
        discount_scope: effectiveDiscountType === "none" ? "per_line" : discountScope,
        order_discount_allocation:
          effectiveDiscountType !== "none" && discountScope === "entire_order"
            ? orderDiscountAllocation
            : "unallocated",
        revenue_mismatch_policy: mismatchPolicy,
        mismatch_tolerance: mismatchTolerance,
        refund_tax_treatment: refundTaxTreatment,
      }
    : null;

  if (restoring) return <DashboardStatus message="Restoring your private analysis…" />;
  if (analysis) {
    return (
      <BusinessDashboard
        analysis={analysis}
        onBack={onBack}
        onNewDataset={() => resetWorkspace(analysis.analysis_id)}
        onCurrencyChange={(selectedCurrency) => switchCurrency(analysis.analysis_id, selectedCurrency)}
      />
    );
  }

  async function handleFile(file: File) {
    setBusy("upload");
    setError(null);
    if (preview) void deleteUpload(preview.upload_id).catch(() => undefined);
    try {
      const result = await uploadCsv(file);
      const initialRevenueMode: RevenueMode = "row_total";
      setPreview(result);
      setRevenueMode(initialRevenueMode);
      setMapping(suggestMapping(result.columns, initialRevenueMode));
      setMappingSuggestions(await fetchMappingSuggestions(result.upload_id, initialRevenueMode));
      setMappingResult(null);
      setValidation(null);
      setQuarantineConfirmed(false);
      setDistinctValues(null);
      setDistinctValuesLoadState("idle");
      setNegativePolicy("invalid");
      setDateFormat("%Y-%m-%d");
      setLatestPeriodComplete(true);
      setStatusMapping({});
      setPaymentStatusMapping({});
      setAssumeAllCompleted(false);
      setDiscountType("none");
      setDiscountScope("per_line");
      setOrderDiscountAllocation("unallocated");
      setMismatchPolicy("warn");
      setMismatchTolerance(0.01);
      setRefundTaxTreatment(null);
    } catch (uploadError) {
      setError(messageFrom(uploadError));
    } finally {
      setBusy(null);
    }
  }

  async function switchCurrency(analysisId: string, selectedCurrency: string) {
    if (selectedCurrency === analysis?.currency) return;
    setRestoring(true);
    try {
      setAnalysis(await fetchAnalysis(analysisId, selectedCurrency));
    } catch (currencyError) {
      setError(messageFrom(currencyError));
    } finally {
      setRestoring(false);
    }
  }

  function handleRevenueMode(mode: RevenueMode) {
    setRevenueMode(mode);
    if (preview) {
      const allowed = new Set(fieldsForMode(mode).map((field) => field.key));
      const retained = Object.fromEntries(
        Object.entries(mapping).filter(([field]) => allowed.has(field)),
      );
      setMapping({ ...suggestMapping(preview.columns, mode), ...retained });
    }
    invalidateReview();
  }

  function handleMapping(field: string, column: string) {
    setMapping((current) => {
      const next = { ...current };
      if (column) next[field] = column;
      else delete next[field];
      return next;
    });
    if (field === "order_status") setStatusMapping({});
    if (field === "payment_status") setPaymentStatusMapping({});
    if (field === "discount" && !column) {
      setDiscountType("none");
      setDiscountScope("per_line");
      setOrderDiscountAllocation("unallocated");
    }
    if (field === "order_status" || field === "payment_status") {
      setDistinctValues(null);
      setDistinctValuesLoadState("idle");
    }
    invalidateReview();
  }

  async function loadDistinctStatusValues(uploadId: string, columns: string[]) {
    if (!columns.length) {
      setDistinctValues(null);
      setDistinctValuesLoadState("idle");
      return;
    }
    setDistinctValues(null);
    setDistinctValuesLoadState("loading");
    try {
      const response = await fetchDistinctValues(uploadId, columns);
      if (columns.some((column) => !response.columns[column])) {
        throw new Error("The status profile response is incomplete");
      }
      setDistinctValues(response);
      setDistinctValuesLoadState("ready");
    } catch {
      setDistinctValues(null);
      setDistinctValuesLoadState("error");
    }
  }

  async function handleValidateMapping() {
    if (!preview) return;
    setBusy("mapping");
    setError(null);
    try {
      const result = await validateMapping(preview.upload_id, mapping, revenueMode);
      setMappingResult(result);
      setValidation(null);
      if (result.valid) {
        await loadDistinctStatusValues(preview.upload_id, statusColumns);
      } else {
        setDistinctValues(null);
        setDistinctValuesLoadState("idle");
      }
    } catch (mappingError) {
      setError(messageFrom(mappingError));
    } finally {
      setBusy(null);
    }
  }

  async function handleValidateData() {
    if (!configuration) return;
    if (!/^[A-Z]{3}$/.test(currency)) {
      setError("Currency must be a three-letter uppercase code such as USD, NGN, or GBP.");
      return;
    }
    setBusy("validation");
    setError(null);
    try {
      setValidation(await validateData(configuration));
      setQuarantineConfirmed(false);
    } catch (validationError) {
      setError(messageFrom(validationError));
    } finally {
      setBusy(null);
    }
  }

  async function handleAnalyze() {
    if (!configuration || !validation?.can_transform) return;
    setBusy("analysis");
    setError(null);
    try {
      const result = await analyzeUpload(
        configuration,
        quarantineConfirmed,
        latestPeriodComplete,
      );
      sessionStorage.setItem("sales-analysis-id", result.analysis_id);
      setAnalysis(result);
      void deleteUpload(configuration.upload_id).catch((cleanupError) => {
        console.warn("Temporary upload cleanup failed; server TTL still applies", cleanupError);
      });
    } catch (analysisError) {
      setError(messageFrom(analysisError));
    } finally {
      setBusy(null);
    }
  }

  function resetWorkspace(analysisId: string) {
    sessionStorage.removeItem("sales-analysis-id");
    setAnalysis(null);
    setPreview(null);
    setMapping({});
    setMappingResult(null);
    setValidation(null);
    setQuarantineConfirmed(false);
    setDistinctValues(null);
    setDistinctValuesLoadState("idle");
    setMappingSuggestions(null);
    setStatusMapping({});
    setPaymentStatusMapping({});
    setRefundTaxTreatment(null);
    setError(null);
    void deleteAnalysis(analysisId).catch(() => undefined);
  }

  function invalidateReview() {
    setMappingResult(null);
    setValidation(null);
    setQuarantineConfirmed(false);
    setDistinctValues(null);
    setDistinctValuesLoadState("idle");
  }

  const currentStep = preview ? (validation ? 3 : mappingResult?.valid ? 3 : 2) : 1;

  return (
    <main className="wizard-page">
      <header className="wizard-header">
        <button type="button" className="icon-button" onClick={onBack} aria-label="Back to data sources">←</button>
        <div>
          <p className="eyebrow">Online retail focus · flexible CSV mapping</p>
          <h1>Build a trustworthy sales dashboard</h1>
        </div>
        <span className="chip">Private · temporary processing</span>
      </header>

      <StepRail current={currentStep} />

      {error ? <div className="notice notice--error" role="alert">{error}</div> : null}

      {!preview ? (
        <UploadPanel busy={busy === "upload"} onFile={handleFile} />
      ) : (
        <div className="wizard-layout">
          <div className="wizard-main">
            <PreviewPanel preview={preview} onReplace={handleFile} />
            <section className="setup-card">
              <SectionHeading
                number="02"
                title="Define what your data means"
                copy="Suggested matches are only a starting point. Review every required field before validation."
              />

              <div className="form-section">
                <span className="form-label">How is revenue represented?</span>
                <div className="choice-grid choice-grid--three">
                  <Choice
                    selected={revenueMode === "row_total"}
                    recommended={mappingSuggestions?.recommended_revenue_mode === "row_total"}
                    title="Row total"
                    copy="Use a final amount such as TotalAmount or NetRevenue when each row has its own sales value."
                    onClick={() => handleRevenueMode("row_total")}
                  />
                  <Choice
                    selected={revenueMode === "unit_price_times_quantity"}
                    recommended={mappingSuggestions?.recommended_revenue_mode === "unit_price_times_quantity"}
                    title="Price × quantity"
                    copy="Use UnitPrice and Quantity when the system must calculate each item row. Configure discounts below."
                    onClick={() => handleRevenueMode("unit_price_times_quantity")}
                  />
                  <Choice
                    selected={revenueMode === "order_total"}
                    recommended={mappingSuggestions?.recommended_revenue_mode === "order_total"}
                    title="Order total"
                    copy="Use when the same full OrderTotal repeats across multiple product rows and must count once."
                    onClick={() => handleRevenueMode("order_total")}
                  />
                </div>
              </div>

              {mappingSuggestions ? (
                <aside className="notice notice--warning">
                  <strong>Mapping assistant recommendation</strong>
                  <p>
                    {mappingSuggestions.recommended_revenue_mode === "unit_price_times_quantity"
                      ? "This file appears to contain unit price and quantity, so price × quantity is recommended."
                      : "Review the suggested field matches before continuing."}
                  </p>
                  <p>{mappingSuggestions.candidates.length} explainable column match(es) are ready to review.</p>
                  <ul className="mapping-assistant-notes">
                    {mappingSuggestions.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                  </ul>
                  <details className="mapping-explanations">
                    <summary>Why these columns were suggested</summary>
                    <ul>
                      {mappingSuggestions.candidates.map((candidate) => (
                        <li key={candidate.field}>
                          <strong>{FIELD_LABELS[candidate.field] ?? candidate.field}</strong>
                          {" → "}{candidate.column} ({Math.round(candidate.confidence * 100)}%) — {candidate.reason}
                        </li>
                      ))}
                    </ul>
                  </details>
                  <button
                    type="button"
                    className="button button--small"
                    onClick={() => {
                      setRevenueMode(mappingSuggestions.recommended_revenue_mode);
                      setMapping(mappingSuggestions.mapping);
                      if (!mappingSuggestions.mapping.discount) {
                        setDiscountType("none");
                        setDiscountScope("per_line");
                        setOrderDiscountAllocation("unallocated");
                      }
                      setMappingSuggestions(null);
                      invalidateReview();
                    }}
                  >
                    Apply recommendations, then review
                  </button>
                </aside>
              ) : null}

              <div className="mapping-list">
                {activeFields.map((field) => (
                  <label className="mapping-row" key={field.key}>
                    <span>
                      <strong>{FIELD_LABELS[field.key]}</strong>
                      <small>{field.required ? "Required" : "Optional"}</small>
                    </span>
                    <select
                      value={mapping[field.key] ?? ""}
                      onChange={(event) => handleMapping(field.key, event.target.value)}
                    >
                      <option value="">Do not map</option>
                      {preview.columns.map((column) => (
                        <option value={column} key={column}>{column}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>

              <div className="settings-grid">
                <label className="field">
                  <span className="form-label">Confirmed date format</span>
                  <select
                    value={DATE_FORMATS.some((option) => option.value === dateFormat) ? dateFormat : "custom"}
                    onChange={(event) => {
                      setDateFormat(event.target.value === "custom" ? "" : event.target.value);
                      invalidateReview();
                    }}
                  >
                    {DATE_FORMATS.map((option) => (
                      <option value={option.value} key={option.value}>{option.label}</option>
                    ))}
                    <option value="custom">Custom Python date format</option>
                  </select>
                  {!DATE_FORMATS.some((option) => option.value === dateFormat) ? (
                    <input
                      value={dateFormat}
                      onChange={(event) => {
                        setDateFormat(event.target.value);
                        invalidateReview();
                      }}
                      placeholder="e.g. %d.%m.%Y"
                    />
                  ) : null}
                  {dateFormatHint ? <small>{dateFormatHint}</small> : null}
                </label>
                <label className="field">
                  <span className="form-label">Currency</span>
                  <input
                    value={currency}
                    maxLength={3}
                    onChange={(event) => {
                      setCurrency(event.target.value.toUpperCase());
                      invalidateReview();
                    }}
                    placeholder="USD"
                  />
                  <small>Three-letter ISO code, for example NGN or GBP</small>
                </label>
              </div>

              <div className="settings-grid">
                <fieldset className="field fieldset-reset">
                  <legend className="form-label">What do negative sales values mean?</legend>
                  <Radio
                    name="negative-policy"
                    checked={negativePolicy === "invalid"}
                    label="Invalid rows — quarantine them"
                    onChange={() => {
                      setNegativePolicy("invalid");
                      invalidateReview();
                    }}
                  />
                  <Radio
                    name="negative-policy"
                    checked={negativePolicy === "refunds"}
                    label="Refunds — include them in net revenue"
                    onChange={() => {
                      setNegativePolicy("refunds");
                      invalidateReview();
                    }}
                  />
                </fieldset>
                <fieldset className="field fieldset-reset">
                  <legend className="form-label">Is the latest month complete?</legend>
                  <Radio
                    name="latest-period"
                    checked={latestPeriodComplete}
                    label="Yes — include it in forecasting"
                    onChange={() => setLatestPeriodComplete(true)}
                  />
                  <Radio
                    name="latest-period"
                    checked={!latestPeriodComplete}
                    label="No — exclude it from forecasting"
                    onChange={() => setLatestPeriodComplete(false)}
                  />
                </fieldset>
              </div>

              <div className="section-actions">
                <button type="button" className="button" disabled={Boolean(busy)} onClick={handleValidateMapping}>
                  {busy === "mapping" ? "Checking mapping…" : "Validate mapping"}
                </button>
              </div>

              {mappingResult ? <MappingResult result={mappingResult} revenueMode={revenueMode} /> : null}

              {mappingResult?.valid ? (
                <div className="rules-panel">
                  <div className="rules-panel__head">
                    <div>
                      <span className="form-label">Retail recognition rules</span>
                      <p>Confirm how operational values affect revenue. Nothing is guessed silently.</p>
                    </div>
                  </div>

                  {statusValuesRequired && distinctValuesLoadState === "loading" ? (
                    <div className="notice" role="status">Loading status values…</div>
                  ) : null}
                  {statusValuesRequired && distinctValuesLoadState === "error" ? (
                    <div className="notice notice--error" role="alert">
                      <p>Status values could not be loaded. Data validation remains disabled.</p>
                      <button
                        type="button"
                        className="button button--small"
                        onClick={() => {
                          if (preview) void loadDistinctStatusValues(preview.upload_id, statusColumns);
                        }}
                      >
                        Retry status values
                      </button>
                    </div>
                  ) : null}

                  {mapping.order_status ? (
                    distinctValuesLoadState === "ready" ? (
                      <StatusClassifier
                        title="Classify every order status"
                        column={mapping.order_status}
                        distinctValues={distinctValues}
                        mapping={statusMapping}
                        options={ORDER_STATUSES}
                        suggestedMapping={suggestOrderStatuses}
                        onApplySuggestions={(suggestions) => {
                          setStatusMapping((current) => ({ ...current, ...suggestions }));
                          setValidation(null);
                        }}
                        onChange={(source, target) => {
                          setStatusMapping((current) => updateClassification(current, source, target));
                          setValidation(null);
                        }}
                      />
                    ) : null
                  ) : (
                    <label className="confirmation-box">
                      <input
                        type="checkbox"
                        checked={assumeAllCompleted}
                        onChange={(event) => {
                          setAssumeAllCompleted(event.target.checked);
                          setValidation(null);
                        }}
                      />
                      <span>
                        <strong>Confirm every row is a completed sale</strong>
                        No order-status column is mapped. Without this confirmation, revenue recognition is blocked.
                      </span>
                    </label>
                  )}

                  {mapping.payment_status && distinctValuesLoadState === "ready" ? (
                    <StatusClassifier
                      title="Classify every payment status"
                      column={mapping.payment_status}
                      distinctValues={distinctValues}
                      mapping={paymentStatusMapping}
                      options={PAYMENT_STATUSES}
                      suggestedMapping={suggestPaymentStatuses}
                      onApplySuggestions={(suggestions) => {
                        setPaymentStatusMapping((current) => ({ ...current, ...suggestions }));
                        setValidation(null);
                      }}
                      onChange={(source, target) => {
                        setPaymentStatusMapping((current) =>
                          updateClassification(current, source, target),
                        );
                        setValidation(null);
                      }}
                    />
                  ) : null}

                  <div className="settings-grid">
                    <label className="field">
                      <span className="form-label">Discount representation</span>
                      <select
                        value={effectiveDiscountType}
                        disabled={!mapping.discount}
                        onChange={(event) => {
                          setDiscountType(event.target.value as DiscountType);
                          setValidation(null);
                        }}
                      >
                        <option value="none">No discount calculation</option>
                        <option value="fixed">Fixed amount</option>
                        <option value="percentage">Percentage</option>
                      </select>
                      <small>
                        {mapping.discount
                          ? "Confirm how the mapped discount values are represented."
                          : "No discount column is mapped, so no discount calculation will be applied."}
                      </small>
                    </label>
                    {effectiveDiscountType !== "none" ? (
                      <label className="field">
                        <span className="form-label">Discount scope</span>
                        <select
                          value={discountScope}
                          onChange={(event) => {
                            setDiscountScope(event.target.value as DiscountScope);
                            setValidation(null);
                          }}
                        >
                          <option value="per_unit">Per unit</option>
                          <option value="per_line">Per line</option>
                          <option value="entire_order">Entire order</option>
                        </select>
                      </label>
                    ) : null}
                  </div>

                  {effectiveDiscountType !== "none" && discountScope === "entire_order" ? (
                    <fieldset className="field fieldset-reset rules-panel__choice">
                      <legend className="form-label">Category treatment for order discounts</legend>
                      <Radio
                        name="discount-allocation"
                        checked={orderDiscountAllocation === "unallocated"}
                        label="Keep unallocated — category totals remain gross"
                        onChange={() => {
                          setOrderDiscountAllocation("unallocated");
                          setValidation(null);
                        }}
                      />
                      <Radio
                        name="discount-allocation"
                        checked={orderDiscountAllocation === "proportional"}
                        label="Allocate proportionally across order lines"
                        onChange={() => {
                          setOrderDiscountAllocation("proportional");
                          setValidation(null);
                        }}
                      />
                    </fieldset>
                  ) : null}

                  {mapping.refund_amount && mapping.tax_amount ? (
                    <fieldset className="field fieldset-reset rules-panel__choice">
                      <legend className="form-label">Does the refund amount include refunded tax?</legend>
                      <Radio
                        name="refund-tax-treatment"
                        checked={refundTaxTreatment === "includes_tax"}
                        label="Yes — split tax out of the refund before revenue is reduced"
                        onChange={() => {
                          setRefundTaxTreatment("includes_tax");
                          setValidation(null);
                        }}
                      />
                      <Radio
                        name="refund-tax-treatment"
                        checked={refundTaxTreatment === "excludes_tax"}
                        label="No — refund amount is only the revenue refund"
                        onChange={() => {
                          setRefundTaxTreatment("excludes_tax");
                          setValidation(null);
                        }}
                      />
                      <small>This cannot be inferred safely from column names. Confirm it from your business system.</small>
                    </fieldset>
                  ) : null}

                  {mapping.revenue && mapping.unit_price && mapping.quantity ? (
                    <div className="settings-grid">
                      <fieldset className="field fieldset-reset">
                        <legend className="form-label">Reported/calculated mismatch</legend>
                        <Radio
                          name="mismatch-policy"
                          checked={mismatchPolicy === "warn"}
                          label="Use selected revenue authority and warn"
                          onChange={() => {
                            setMismatchPolicy("warn");
                            setValidation(null);
                          }}
                        />
                        <Radio
                          name="mismatch-policy"
                          checked={mismatchPolicy === "quarantine"}
                          label="Quarantine rows outside tolerance"
                          onChange={() => {
                            setMismatchPolicy("quarantine");
                            setValidation(null);
                          }}
                        />
                      </fieldset>
                      <label className="field">
                        <span className="form-label">Allowed amount difference</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={mismatchTolerance}
                          onChange={(event) => {
                            setMismatchTolerance(Math.max(Number(event.target.value), 0));
                            setValidation(null);
                          }}
                        />
                        <small>Compared in the row currency, for example 0.01.</small>
                      </label>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </section>

            {mappingResult?.valid ? (
              <section className="setup-card">
                <SectionHeading
                  number="03"
                  title="Verify data quality"
                  copy="We test every mapped value before calculations. Invalid rows stay visible and traceable."
                />
                {!validation ? (
                  <div className="section-actions section-actions--start">
                    <button
                      type="button"
                      className="button"
                      disabled={Boolean(busy) || !statusValuesReady}
                      onClick={handleValidateData}
                    >
                      {busy === "validation" ? "Validating every row…" : "Validate data"}
                    </button>
                  </div>
                ) : (
                  <ValidationResult
                    validation={validation}
                    confirmed={quarantineConfirmed}
                    onConfirm={setQuarantineConfirmed}
                  />
                )}

                {validation?.can_transform ? (
                  <div className="section-actions">
                    <button
                      type="button"
                      className="button button--hero"
                      disabled={Boolean(busy) || (validation.requires_confirmation && !quarantineConfirmed)}
                      onClick={handleAnalyze}
                    >
                      {busy === "analysis" ? "Building dashboard…" : "Generate intelligence dashboard"}
                    </button>
                  </div>
                ) : null}
              </section>
            ) : null}
          </div>
          <aside className="privacy-card">
            <span className="privacy-card__icon" aria-hidden="true">⌁</span>
            <strong>Temporary by design</strong>
            <p>The original CSV expires after 30 minutes and is removed early after analysis succeeds.</p>
            <hr />
            <span>Maximum upload</span><strong>10 MiB</strong>
            <span>Analysis session</span><strong>2 hours</strong>
          </aside>
        </div>
      )}
    </main>
  );
}

function UploadPanel({ busy, onFile }: { busy: boolean; onFile: (file: File) => void }) {
  const [dragging, setDragging] = useState(false);
  return (
    <section className="upload-stage">
      <SectionHeading
        number="01"
        title="Upload transaction data"
        copy="Start with an order export containing order, date, customer, and revenue information. Other sales CSVs can use the same mapping flow when these meanings are present."
      />
      <label
        className={`dropzone${dragging ? " dropzone--active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void onFile(file);
        }}
      >
        <input
          type="file"
          accept=".csv,text/csv"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void onFile(file);
          }}
        />
        <span className="dropzone__icon" aria-hidden="true">↑</span>
        <strong>{busy ? "Reading your CSV…" : "Drop your sales CSV here"}</strong>
        <span>or click to choose a file · maximum 10 MiB</span>
      </label>
      <div className="upload-requirements">
        <span>Required meanings: order, date, customer, revenue</span>
        <span>Optional: product/SKU, quantity, unit, category, region</span>
      </div>
    </section>
  );
}

function PreviewPanel({ preview, onReplace }: { preview: CsvPreviewResponse; onReplace: (file: File) => void }) {
  return (
    <section className="setup-card preview-card">
      <div className="preview-card__head">
        <div>
          <p className="eyebrow">Upload received</p>
          <h2>{preview.filename}</h2>
          <p>{preview.row_count.toLocaleString()} rows · {preview.column_count} columns</p>
        </div>
        <label className="button button--secondary button--small">
          Replace file
          <input
            className="visually-hidden"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onReplace(file);
            }}
          />
        </label>
      </div>
      <div className="preview-table-wrap">
        <table className="preview-table">
          <thead><tr>{preview.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
          <tbody>
            {preview.sample_rows.map((row, index) => (
              <tr key={index}>
                {preview.columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="preview-card__note">Preview shows the first five rows. Direct personal identifiers are masked; business IDs such as “001” remain text.</p>
    </section>
  );
}

function StepRail({ current }: { current: number }) {
  return (
    <ol className="step-rail" aria-label="Analysis progress">
      {["Upload", "Map", "Validate", "Dashboard"].map((label, index) => {
        const number = index + 1;
        return (
          <li className={number <= current ? "step-rail__item step-rail__item--active" : "step-rail__item"} key={label}>
            <span>{number}</span>{label}
          </li>
        );
      })}
    </ol>
  );
}

function SectionHeading({ number, title, copy }: { number: string; title: string; copy: string }) {
  return (
    <div className="section-heading">
      <span>{number}</span>
      <div><h2>{title}</h2><p>{copy}</p></div>
    </div>
  );
}

function Choice({ selected, recommended, title, copy, onClick }: { selected: boolean; recommended: boolean; title: string; copy: string; onClick: () => void }) {
  return (
    <button type="button" className={`choice${selected ? " choice--selected" : ""}`} onClick={onClick} aria-pressed={selected}>
      <span className="choice__head"><strong>{title}</strong>{recommended ? <em>Recommended</em> : null}</span>
      <span>{copy}</span>
    </button>
  );
}

function Radio({ name, checked, label, onChange }: { name: string; checked: boolean; label: string; onChange: () => void }) {
  return (
    <label className="radio-row"><input type="radio" name={name} checked={checked} onChange={onChange} /><span>{label}</span></label>
  );
}

function StatusClassifier<T extends string>({
  title,
  column,
  distinctValues,
  mapping,
  options,
  suggestedMapping,
  onApplySuggestions,
  onChange,
}: {
  title: string;
  column: string;
  distinctValues: DistinctValuesResponse | null;
  mapping: Record<string, T>;
  options: Array<{ value: T; label: string }>;
  suggestedMapping: (values: string[]) => Record<string, T>;
  onApplySuggestions: (suggestions: Record<string, T>) => void;
  onChange: (source: string, target: T | "") => void;
}) {
  const profile = distinctValues?.columns[column];
  if (!profile) {
    return <div className="notice notice--warning">Status values could not be loaded. Validate the mapping again.</div>;
  }
  return (
    <div className="classification">
      <div className="classification__head">
        <strong>{title}</strong>
        <span>{profile.unique_count} distinct value{profile.unique_count === 1 ? "" : "s"}</span>
      </div>
      <button
        type="button"
        className="button button--small"
        onClick={() => onApplySuggestions(suggestedMapping(profile.values))}
      >
        Apply common-value suggestions
      </button>
      {profile.values.map((source) => (
        <label className="classification__row" key={source}>
          <code>{source}</code>
          <span aria-hidden="true">→</span>
          <select
            value={mapping[source] ?? ""}
            onChange={(event) => onChange(source, event.target.value as T | "")}
          >
            <option value="">Choose meaning</option>
            {options.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      ))}
      {profile.blank_count ? (
        <p className="classification__warning">
          {profile.blank_count.toLocaleString()} blank status value(s) will be quarantined.
        </p>
      ) : null}
      {profile.truncated ? (
        <p className="classification__warning">
          More than 100 distinct values exist. This column is probably not a status field.
        </p>
      ) : null}
    </div>
  );
}

function MappingResult({ result, revenueMode }: { result: SchemaMappingResponse; revenueMode: RevenueMode }) {
  const revenueCandidate = result.unmapped_columns.find((column) =>
    ALIASES.revenue.includes(normalizeHeader(column)),
  );
  const revenueHint = !result.valid && result.missing_required_fields.includes("revenue")
    ? revenueMode === "order_total"
      ? "Select the column containing the full order total. Use this mode only when that total repeats across item rows."
      : "Select the final amount for each row. If your file only has unit price and quantity, choose Price × quantity above."
    : null;
  return (
    <div className={`notice ${result.valid ? "notice--success" : "notice--error"}`}>
      <strong>{result.valid ? "Mapping is valid" : "Mapping needs attention"}</strong>
      {[...result.errors, ...result.warnings].map((message) => <p key={message}>{message}</p>)}
      {revenueHint ? <p><strong>What to do:</strong> {revenueHint}</p> : null}
      {revenueHint && revenueCandidate ? (
        <p>
          <strong>Where to fix it:</strong> In the <strong>{FIELD_LABELS.revenue}</strong> dropdown,
          select <code>{revenueCandidate}</code>.
        </p>
      ) : null}
    </div>
  );
}

function normalizeHeader(value: string): string {
  return value.toLowerCase().replaceAll(/[^a-z0-9]/g, "");
}

function ValidationResult({ validation, confirmed, onConfirm }: { validation: DataValidationResponse; confirmed: boolean; onConfirm: (value: boolean) => void }) {
  const quality = validation.data_quality;
  return (
    <div className="validation-result">
      <div className="validation-stats">
        <div><span>Total rows</span><strong>{validation.total_rows.toLocaleString()}</strong></div>
        <div><span>Valid rows</span><strong className="text-positive">{validation.valid_rows.toLocaleString()}</strong></div>
        <div><span>Invalid rows</span><strong className={validation.invalid_rows ? "text-warning" : "text-positive"}>{validation.invalid_rows.toLocaleString()}</strong></div>
      </div>
      <div className={`data-quality-summary data-quality-summary--${quality.status}`} role="status">
        <div>
          <span className="data-quality-summary__label">Data readiness</span>
          <strong>{dataQualityLabel(quality.status)}</strong>
        </div>
        <span>{quality.invalid_row_percentage.toFixed(1)}% invalid</span>
        <p>{quality.message}</p>
        {quality.restricted_outputs.length > 0 ? (
          <p>
            <strong>Not decision-ready:</strong> {quality.restricted_outputs.join(", ")}.
          </p>
        ) : null}
      </div>
      {validation.blocking_errors.length > 0 ? (
        <div className="notice notice--error">{validation.blocking_errors.join(" ")}</div>
      ) : null}
      {validation.sample_issues.length > 0 ? (
        <div className="issue-list">
          <div className="issue-list__head"><strong>Sample issues</strong><span>First {validation.sample_issues.length}</span></div>
          {validation.sample_issues.map((issue) => (
            <div className="issue-row" key={`${issue.row_number}-${issue.field}-${issue.code}`}>
              <span>{csvRowLabel(issue.row_number)}</span><strong>{issue.field}</strong><span>{issue.message}</span>
            </div>
          ))}
        </div>
      ) : <div className="notice notice--success"><strong>Every row passed validation.</strong></div>}
      {quality.correction_actions.length > 0 ? (
        <RepairGuide actions={quality.correction_actions} />
      ) : null}
      {validation.requires_confirmation ? (
        <label className="confirmation-box">
          <input type="checkbox" checked={confirmed} onChange={(event) => onConfirm(event.target.checked)} />
          <span><strong>Quarantine {validation.invalid_rows.toLocaleString()} invalid rows</strong>They will be excluded from calculations and preserved in a downloadable audit file.</span>
        </label>
      ) : null}
    </div>
  );
}

function dataQualityLabel(status: DataValidationResponse["data_quality"]["status"]): string {
  const labels = {
    normal: "Decision-ready",
    caution: "Decision-ready with caution",
    preview: "Preview only",
    blocked: "Blocked",
  };
  return labels[status];
}

function RepairGuide({ actions }: { actions: DataValidationResponse["data_quality"]["correction_actions"] }) {
  return (
    <div className="repair-guide">
      <div className="repair-guide__head">
        <strong>How to correct the CSV</strong>
        <span>{actions.length} issue group{actions.length === 1 ? "" : "s"}</span>
      </div>
      <ul className="repair-list">
        {actions.map((action) => (
          <li key={`${action.field}-${action.issue_code}-${action.problem}`}>
            <div className="repair-list__title">
              <strong>{action.source_column ?? action.field.replaceAll("_", " ")}</strong>
              <span>{action.affected_rows.toLocaleString()} affected row{action.affected_rows === 1 ? "" : "s"}</span>
            </div>
            <p>{action.problem}</p>
            <p><strong>Fix:</strong> {action.instruction}</p>
            {action.sample_row_numbers.length > 0 ? (
              <small>{repairLocation(action)}</small>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function repairLocation(action: DataValidationResponse["data_quality"]["correction_actions"][number]): string {
  const column = action.source_column ?? action.field.replaceAll("_", " ");
  const location = csvRowLocations(action.sample_row_numbers, column);
  if (action.affected_rows > action.sample_row_numbers.length) {
    return `First ${action.sample_row_numbers.length} affected locations: ${location}. Download the quarantine CSV for all affected rows.`;
  }
  return `Affected location: ${location}.`;
}

function csvRowLabel(csvLineNumber: number): string {
  return `CSV line ${csvLineNumber} (data row ${csvLineNumber - 1})`;
}

function csvRowLocations(csvLineNumbers: number[], column: string): string {
  const lineNumbers = csvLineNumbers.join(", ");
  const dataRowNumbers = csvLineNumbers.map((lineNumber) => lineNumber - 1).join(", ");
  const lineLabel = csvLineNumbers.length === 1 ? "line" : "lines";
  const dataLabel = csvLineNumbers.length === 1 ? "row" : "rows";
  return `CSV ${lineLabel} ${lineNumbers} (data ${dataLabel} ${dataRowNumbers}) · ${column} column`;
}

function fieldsForMode(mode: RevenueMode): Array<{ key: string; required: boolean }> {
  const base = ["order_id", "order_date", "customer_id"];
  const required = mode === "unit_price_times_quantity" ? [...base, "unit_price", "quantity"] : [...base, "revenue"];
  const optional = mode === "row_total"
    ? [
        "unit_price", "quantity", "discount", "product_id", "product_name",
        "unit_of_measure", "product_category", "state_or_region",
        "order_status", "payment_status", "refund_amount", "returned_quantity",
        "payment_amount",
        "recognition_date", "refund_date", "tax_amount", "shipping_amount",
        "chargeback_amount", "currency", "line_item_id",
      ]
    : mode === "unit_price_times_quantity"
      ? [
          "revenue", "discount", "product_id", "product_name", "unit_of_measure",
          "product_category", "state_or_region", "order_status",
          "payment_status", "refund_amount", "returned_quantity", "recognition_date",
          "payment_amount",
          "refund_date", "tax_amount", "shipping_amount", "chargeback_amount", "currency",
          "line_item_id",
        ]
      : [
          "discount", "state_or_region", "order_status", "payment_status", "refund_amount",
          "payment_amount",
          "recognition_date", "refund_date", "tax_amount", "shipping_amount",
          "chargeback_amount", "currency",
        ];
  return [...required.map((key) => ({ key, required: true })), ...optional.map((key) => ({ key, required: false }))];
}

function updateClassification<T extends string>(
  current: Record<string, T>,
  source: string,
  target: T | "",
): Record<string, T> {
  const next = { ...current };
  if (target) next[source] = target;
  else delete next[source];
  return next;
}

function suggestOrderStatuses(values: string[]): Record<string, StandardOrderStatus> {
  const matches: Record<string, StandardOrderStatus> = {};
  for (const value of values) {
    const normalized = normalize(value);
    if (["completed", "complete", "delivered", "fulfilled", "done"].includes(normalized)) {
      matches[value] = "completed";
    } else if (["pending", "processing", "confirmed", "shipped", "awaitingpayment"].includes(normalized)) {
      matches[value] = "pending";
    } else if (["cancelled", "canceled", "voided"].includes(normalized)) {
      matches[value] = "cancelled";
    } else if (["returned", "return", "refunded"].includes(normalized)) {
      matches[value] = "returned";
    }
  }
  return matches;
}

function suggestPaymentStatuses(values: string[]): Record<string, StandardPaymentStatus> {
  const matches: Record<string, StandardPaymentStatus> = {};
  for (const value of values) {
    const normalized = normalize(value);
    if (["paid", "successful", "success"].includes(normalized)) matches[value] = "paid";
    else if (["refunded", "refund"].includes(normalized)) matches[value] = "refunded";
    else if (["pending", "unpaid", "notpaid"].includes(normalized)) matches[value] = "pending";
    else if (["failed", "failure"].includes(normalized)) matches[value] = "failed";
    else if (["voided", "void"].includes(normalized)) matches[value] = "voided";
    else if (["disputed", "dispute"].includes(normalized)) matches[value] = "disputed";
  }
  return matches;
}

function suggestMapping(columns: string[], mode: RevenueMode): Record<string, string> {
  const mapping: Record<string, string> = {};
  const used = new Set<string>();
  for (const field of fieldsForMode(mode)) {
    const aliases = ALIASES[field.key] ?? [];
    const match = columns.find((column) => !used.has(column) && aliases.includes(normalize(column)));
    if (match) {
      mapping[field.key] = match;
      used.add(match);
    }
  }
  return mapping;
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function suggestDateFormat(
  preview: CsvPreviewResponse | null,
  dateColumn: string | undefined,
): string | null {
  if (!preview || !dateColumn) return null;
  const values = preview.sample_rows
    .map((row) => String(row[dateColumn] ?? "").trim())
    .filter(Boolean);
  if (values.length === 0) return null;
  if (values.every((value) => /^\d{4}-\d{2}-\d{2}$/.test(value))) {
    return "Sample pattern suggests %Y-%m-%d. Confirm before continuing.";
  }
  if (values.every((value) => /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value))) {
    return "Sample pattern suggests %Y-%m-%d %H:%M:%S. Confirm before continuing.";
  }
  if (values.every((value) => /^\d{2}\/\d{2}\/\d{4}$/.test(value))) {
    const pairs = values.map((value) => value.split("/").slice(0, 2).map(Number));
    if (pairs.some(([first]) => first > 12)) {
      return "Sample pattern suggests %d/%m/%Y. Confirm before continuing.";
    }
    if (pairs.some(([, second]) => second > 12)) {
      return "Sample pattern suggests %m/%d/%Y. Confirm before continuing.";
    }
    return "This sample is ambiguous: it could be day/month or month/day. You must confirm it.";
  }
  return "The sample does not match a common pattern. Choose or enter the exact format.";
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}
