import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..", "..");
const infographicRoot = path.resolve(repoRoot, "infographics");

const canonicalPath = path.resolve(
  repoRoot,
  "artifacts/canonical_datasets/MCD_canonical_dataset_20260223T101320Z.json",
);
const toolCallsPath = path.resolve(
  repoRoot,
  "artifacts/canonical_datasets/smoke_20260223T101309Z_tool_calls.jsonl",
);
const runLogPath = path.resolve(repoRoot, "artifacts/run_logs/smoke_20260223T101309Z.log");

const outRoot = path.resolve(repoRoot, "artifacts/infographics/mcd_poc_client_ready");
const outPngVega = path.resolve(outRoot, "png/vega_lite");
const outPngEcharts = path.resolve(outRoot, "png/echarts");

const colors = {
  navy: "#0f2740",
  blue: "#2f6cad",
  teal: "#1f8a70",
  orange: "#cf6a00",
  slate: "#7a8da6",
  green: "#2d8a34",
  red: "#bf2f2f",
  purple: "#5b55d8",
  bg: "#eef2f7",
  ink: "#102a43",
  muted: "#5f6f84",
};

const echartsFont = {
  title: 30,
  subtitle: 18,
  tooltip: 15,
  legend: 17,
  axisLabel: 16,
  axisName: 17,
  dataLabel: 16,
  annotation: 15,
};

const secFilingUrl =
  "https://www.sec.gov/Archives/edgar/data/63908/000006390825000026/mcd-20250331.htm";
const secReportMirror = "https://sec.report/Document/0000063908-25-000026/";

const charts = [
  { id: "segment_revenue_mix_q1_2025", title: "Revenue Mix by Segment (Q1 2025, USD mm)" },
  { id: "segment_revenue_yoy_q1", title: "Segment Revenue (Q1 2024 vs Q1 2025, USD mm)" },
  { id: "comp_sales_by_segment", title: "Comparable Sales by Segment (Q1 2025, %)" },
  { id: "ownership_mix_q1_2025", title: "Restaurant Ownership Mix (Q1 2025)" },
  { id: "franchise_mix_q1_2025", title: "Franchise Type Mix (Q1 2025)" },
  { id: "dcf_outcomes_vs_market", title: "DCF Outcomes vs Market Price (USD/share)" },
  { id: "scenario_weights", title: "Scenario Weights from Run (%)" },
  { id: "scenario_gap_vs_market", title: "Scenario Discount/Premium vs Market (%)" },
  { id: "comps_ev_ebit", title: "Peer Comps EV/EBIT (x)" },
  { id: "comps_ev_sales", title: "Peer Comps EV/Sales (x)" },
  { id: "sensitivity_heatmap", title: "Sensitivity Grid (Value/share by WACC x g)" },
];

const secContext = {
  segmentRevenueQ12025: [
    { segment: "U.S.", revenueUsdMm: 2494.0 },
    { segment: "IOM", revenueUsdMm: 2916.0 },
    { segment: "IDL", revenueUsdMm: 546.0 },
  ],
  segmentRevenueQ12024: [
    { segment: "U.S.", revenueUsdMm: 2504.0 },
    { segment: "IOM", revenueUsdMm: 2806.0 },
    { segment: "IDL", revenueUsdMm: 537.0 },
  ],
  compSalesQ12025Pct: [
    { segment: "U.S.", compSalesPct: -3.6 },
    { segment: "IOM", compSalesPct: -1.0 },
    { segment: "IDL", compSalesPct: 3.5 },
  ],
  ownershipCountsQ12025: [
    { ownershipType: "Franchised", restaurantCount: 41720 },
    { ownershipType: "Company-operated", restaurantCount: 2036 },
  ],
  franchiseMixQ12025: [
    { franchiseType: "Conventional", sharePct: 84.0 },
    { franchiseType: "Developmental licensed", sharePct: 16.0 },
  ],
};

function parseJson(pathValue) {
  return JSON.parse(readFileSync(pathValue, "utf-8"));
}

function parseJsonl(pathValue) {
  return readFileSync(pathValue, "utf-8")
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

function unwrap(value) {
  let out = value;
  while (Array.isArray(out) && out.length === 1) {
    out = out[0];
  }
  return out;
}

function formatNumber(value, digits = 1) {
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function roundTo(value, digits = 2) {
  return Number(Number(value).toFixed(digits));
}

function signedPct(value, digits = 2) {
  const sign = Number(value) > 0 ? "+" : "";
  return `${sign}${formatNumber(value, digits)}%`;
}

function getPayload(call) {
  if (call && call.result && typeof call.result === "object") {
    if (call.result.result && typeof call.result.result === "object") {
      return call.result.result;
    }
    return call.result;
  }
  return {};
}

function findLastPayloadWithKey(calls, key) {
  for (let i = calls.length - 1; i >= 0; i -= 1) {
    const payload = getPayload(calls[i]);
    if (Object.prototype.hasOwnProperty.call(payload, key)) {
      return payload;
    }
  }
  throw new Error(`Unable to find key in tool-call payloads: ${key}`);
}

function isNumericMatrix(value) {
  if (!Array.isArray(value) || value.length === 0) return false;
  if (!Array.isArray(value[0])) return false;
  return value.every(
    (row) => Array.isArray(row) && row.every((cell) => Number.isFinite(Number(cell))),
  );
}

function findLastNumericMatrix(calls, key) {
  for (let i = calls.length - 1; i >= 0; i -= 1) {
    const payload = getPayload(calls[i]);
    if (!Object.prototype.hasOwnProperty.call(payload, key)) continue;
    if (isNumericMatrix(payload[key])) return payload[key];
  }
  throw new Error(`Unable to find numeric matrix for key: ${key}`);
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }
  return sorted[middle];
}

function buildBundle() {
  const canonicalRaw = parseJson(canonicalPath);
  const canonical = canonicalRaw.canonical_dataset;
  const calls = parseJsonl(toolCallsPath);
  const namedReadCalls = calls.filter(
    (call) => call.tool === "sheets_read_named_ranges" && call.status === "ok",
  );

  if (namedReadCalls.length === 0) {
    throw new Error("No successful sheets_read_named_ranges calls found.");
  }

  const dcfPayload = findLastPayloadWithKey(namedReadCalls, "out_value_ps_weighted");
  const compsPayload = findLastPayloadWithKey(namedReadCalls, "comps_table_full");
  const sensVectorPayload = findLastPayloadWithKey(namedReadCalls, "sens_wacc_vector");
  const eqPayload = findLastPayloadWithKey(namedReadCalls, "out_equity_value_weighted");
  const sensitivityMatrix = findLastNumericMatrix(namedReadCalls, "sens_grid_values");

  const marketPrice = Number(unwrap(dcfPayload.inp_px));
  const scenarioRows = [
    {
      scenario: "Pess",
      valuePsUsd: Number(unwrap(dcfPayload.out_value_ps_pess)),
      weightPct: Number(unwrap(dcfPayload.inp_w_pess)) * 100,
    },
    {
      scenario: "Base",
      valuePsUsd: Number(unwrap(dcfPayload.out_value_ps_base)),
      weightPct: Number(unwrap(dcfPayload.inp_w_base)) * 100,
    },
    {
      scenario: "Opt",
      valuePsUsd: Number(unwrap(dcfPayload.out_value_ps_opt)),
      weightPct: Number(unwrap(dcfPayload.inp_w_opt)) * 100,
    },
    {
      scenario: "Weighted",
      valuePsUsd: Number(unwrap(dcfPayload.out_value_ps_weighted)),
      weightPct: 100,
    },
  ].map((row) => ({
    ...row,
    gapVsMarketPct: ((row.valuePsUsd / marketPrice) - 1) * 100,
  }));

  const compsTable = compsPayload.comps_table_full;
  const headers = compsTable[0];
  const compsRows = compsTable.slice(1).map((row) => {
    const obj = {};
    headers.forEach((header, idx) => {
      obj[header] = row[idx];
    });
    obj["Market Cap ($B)"] = Number(obj["Market Cap ($B)"]);
    obj["Revenue ($B)"] = Number(obj["Revenue ($B)"]);
    obj["EBIT ($B)"] = Number(obj["EBIT ($B)"]);
    obj["EV/Sales"] = Number(obj["EV/Sales"]);
    obj["EV/EBIT"] = Number(obj["EV/EBIT"]);
    return obj;
  });

  const waccVector = unwrap(sensVectorPayload.sens_wacc_vector).map((v) =>
    Number(unwrap(v)),
  );
  const gVector = unwrap(sensVectorPayload.sens_terminal_g_vector).map((v) => Number(v));
  const sensitivityGrid = [];
  for (let i = 0; i < waccVector.length; i += 1) {
    for (let j = 0; j < gVector.length; j += 1) {
      sensitivityGrid.push({
        waccPct: waccVector[i] * 100,
        terminalGPct: gVector[j] * 100,
        valuePsUsd: Number(sensitivityMatrix[i][j]),
      });
    }
  }

  const segLong = [];
  for (const row of secContext.segmentRevenueQ12024) {
    segLong.push({
      segment: row.segment,
      quarter: "Q1 2024",
      revenueUsdMm: row.revenueUsdMm,
    });
  }
  for (const row of secContext.segmentRevenueQ12025) {
    segLong.push({
      segment: row.segment,
      quarter: "Q1 2025",
      revenueUsdMm: row.revenueUsdMm,
    });
  }

  const ownershipTotal = secContext.ownershipCountsQ12025.reduce(
    (acc, row) => acc + row.restaurantCount,
    0,
  );

  const now = new Date().toISOString();
  const runId = calls[0]?.run_id || "smoke_20260223T101309Z";

  return {
    meta: {
      generatedAtUtc: now,
      runId,
      ticker: canonical.ticker,
      companyName: canonical.fundamentals.company_name,
      status: "COMPLETED",
    },
    charts,
    marketPriceUsd: marketPrice,
    fundamentals: {
      revenueTtmUsdB: canonical.fundamentals.revenue_ttm / 1000,
      ebitTtmUsdB: canonical.fundamentals.ebit_ttm / 1000,
      ebitMarginPct:
        (canonical.fundamentals.ebit_ttm / canonical.fundamentals.revenue_ttm) * 100,
      marketCapUsdB: canonical.market.market_cap / 1000,
      cashUsdB: canonical.fundamentals.cash / 1000,
      debtUsdB: canonical.fundamentals.debt / 1000,
    },
    valuation: {
      outWaccPct: Number(unwrap(dcfPayload.OUT_WACC)) * 100,
      outTerminalGPct: Number(unwrap(dcfPayload.out_terminal_g)) * 100,
      weightedEquityValueUsdB: Number(unwrap(eqPayload.out_equity_value_weighted)) / 1000,
      weightedEnterpriseValueUsdB:
        Number(unwrap(eqPayload.out_enterprise_value_weighted)) / 1000,
      scenarios: scenarioRows,
      scenarioWeights: scenarioRows.filter((r) =>
        ["Pess", "Base", "Opt"].includes(r.scenario),
      ),
    },
    peers: {
      rows: compsRows,
      evEbitMedian: median(compsRows.map((r) => r["EV/EBIT"])),
      evSalesMedian: median(compsRows.map((r) => r["EV/Sales"])),
    },
    sec: {
      segmentRevenueQ12024: secContext.segmentRevenueQ12024,
      segmentRevenueQ12025: secContext.segmentRevenueQ12025,
      segmentRevenueLong: segLong,
      compSalesQ12025Pct: secContext.compSalesQ12025Pct,
      ownershipCountsQ12025: secContext.ownershipCountsQ12025,
      ownershipTotal,
      franchiseMixQ12025: secContext.franchiseMixQ12025,
    },
    sensitivity: {
      waccVectorPct: waccVector.map((v) => v * 100),
      terminalGVectorPct: gVector.map((v) => v * 100),
      grid: sensitivityGrid,
    },
    artifacts: {
      canonicalDatasetPath: path.relative(repoRoot, canonicalPath),
      toolCallsPath: path.relative(repoRoot, toolCallsPath),
      runLogPath: path.relative(repoRoot, runLogPath),
      secFilingUrl,
      secReportMirror,
      canonicalCitations: canonical.citations || [],
    },
  };
}

function baseVegaConfig() {
  return {
    width: 1760,
    height: 760,
    config: {
      background: "#ffffff",
      font: "Avenir Next, Segoe UI, Arial, sans-serif",
      axis: {
        labelColor: colors.ink,
        titleColor: colors.ink,
        labelFontSize: 16,
        titleFontSize: 18,
        labelLimit: 360,
        gridColor: "#e7edf5",
        domainColor: "#cdd8e6",
      },
      legend: {
        labelColor: colors.ink,
        titleColor: colors.ink,
        labelFontSize: 15,
        titleFontSize: 16,
      },
      title: {
        color: colors.ink,
        fontSize: 30,
        fontWeight: "bold",
        anchor: "start",
      },
      view: { stroke: null },
    },
  };
}

function vegaSpec(id, bundle) {
  const base = baseVegaConfig();
  const dcf = bundle.valuation.scenarios;
  const marketPrice = bundle.marketPriceUsd;

  const specs = {
    segment_revenue_mix_q1_2025: {
      ...base,
      title: "Revenue Mix by Segment (Q1 2025)",
      data: { values: bundle.sec.segmentRevenueQ12025 },
      transform: [{ calculate: "datum.revenueUsdMm / 5956 * 100", as: "sharePct" }],
      layer: [
        {
          mark: {
            type: "arc",
            innerRadius: 190,
            outerRadius: 320,
            stroke: "#ffffff",
            strokeWidth: 3,
          },
          encoding: {
            theta: { field: "revenueUsdMm", type: "quantitative" },
            color: {
              field: "segment",
              scale: {
                domain: ["U.S.", "IOM", "IDL"],
                range: [colors.blue, colors.teal, colors.orange],
              },
              legend: { title: "Segment", orient: "right" },
            },
            tooltip: [
              { field: "segment", type: "nominal" },
              { field: "revenueUsdMm", type: "quantitative", title: "Revenue (USD mm)" },
              { field: "sharePct", type: "quantitative", title: "Share %", format: ".1f" },
            ],
          },
        },
        {
          data: { values: [{ label: "USD 5,956mm\nTotal" }] },
          mark: {
            type: "text",
            align: "center",
            baseline: "middle",
            color: colors.navy,
            fontSize: 46,
            fontWeight: 800,
          },
          encoding: { text: { field: "label" } },
        },
      ],
    },
    segment_revenue_yoy_q1: {
      ...base,
      title: "Segment Revenue (Q1 2024 vs Q1 2025)",
      data: { values: bundle.sec.segmentRevenueLong },
      mark: { type: "bar", cornerRadiusTopLeft: 6, cornerRadiusTopRight: 6 },
      encoding: {
        x: { field: "segment", type: "nominal", axis: { title: "Segment" } },
        xOffset: { field: "quarter" },
        y: {
          field: "revenueUsdMm",
          type: "quantitative",
          axis: { title: "Revenue (USD mm)" },
        },
        color: {
          field: "quarter",
          scale: { domain: ["Q1 2024", "Q1 2025"], range: [colors.slate, colors.blue] },
          legend: { title: "Quarter" },
        },
      },
    },
    comp_sales_by_segment: {
      ...base,
      title: "Comparable Sales by Segment (Q1 2025)",
      data: { values: bundle.sec.compSalesQ12025Pct },
      mark: { type: "bar", cornerRadiusEnd: 6 },
      encoding: {
        y: {
          field: "segment",
          type: "ordinal",
          sort: ["U.S.", "IOM", "IDL"],
          axis: { title: null },
        },
        x: {
          field: "compSalesPct",
          type: "quantitative",
          axis: { title: "Comparable Sales (%)" },
        },
        color: {
          condition: { test: "datum.compSalesPct >= 0", value: colors.green },
          value: colors.red,
        },
      },
    },
    ownership_mix_q1_2025: {
      ...base,
      title: "Restaurant Ownership Mix (Q1 2025)",
      data: { values: bundle.sec.ownershipCountsQ12025 },
      transform: [
        {
          calculate: `datum.restaurantCount / ${bundle.sec.ownershipTotal} * 100`,
          as: "sharePct",
        },
      ],
      layer: [
        {
          mark: {
            type: "arc",
            innerRadius: 190,
            outerRadius: 320,
            stroke: "#ffffff",
            strokeWidth: 3,
          },
          encoding: {
            theta: { field: "restaurantCount", type: "quantitative" },
            color: {
              field: "ownershipType",
              scale: {
                domain: ["Franchised", "Company-operated"],
                range: [colors.green, "#9ca3af"],
              },
            },
            tooltip: [
              { field: "ownershipType" },
              { field: "restaurantCount", title: "Restaurants" },
              { field: "sharePct", title: "Share %", format: ".1f" },
            ],
          },
        },
        {
          data: { values: [{ label: "43,756\nRestaurants" }] },
          mark: {
            type: "text",
            align: "center",
            baseline: "middle",
            color: colors.navy,
            fontSize: 44,
            fontWeight: 800,
          },
          encoding: { text: { field: "label" } },
        },
      ],
    },
    franchise_mix_q1_2025: {
      ...base,
      title: "Franchise Type Mix (Q1 2025)",
      data: { values: bundle.sec.franchiseMixQ12025 },
      mark: {
        type: "arc",
        innerRadius: 190,
        outerRadius: 320,
        stroke: "#ffffff",
        strokeWidth: 3,
      },
      encoding: {
        theta: { field: "sharePct", type: "quantitative" },
        color: {
          field: "franchiseType",
          scale: {
            domain: ["Conventional", "Developmental licensed"],
            range: [colors.teal, colors.purple],
          },
        },
      },
    },
    dcf_outcomes_vs_market: {
      ...base,
      title: "DCF Outcomes vs Market Price",
      layer: [
        {
          data: { values: dcf },
          mark: { type: "bar", cornerRadiusTopLeft: 6, cornerRadiusTopRight: 6 },
          encoding: {
            x: {
              field: "scenario",
              type: "nominal",
              sort: ["Pess", "Base", "Opt", "Weighted"],
              axis: { title: null },
            },
            y: {
              field: "valuePsUsd",
              type: "quantitative",
              axis: { title: "Value (USD/share)" },
            },
            color: {
              field: "scenario",
              scale: {
                domain: ["Pess", "Base", "Opt", "Weighted"],
                range: [colors.orange, colors.blue, colors.teal, colors.navy],
              },
            },
          },
        },
        {
          data: { values: [{ marketPrice }] },
          mark: { type: "rule", strokeDash: [10, 8], color: colors.red, strokeWidth: 3 },
          encoding: { y: { field: "marketPrice", type: "quantitative" } },
        },
      ],
    },
    scenario_weights: {
      ...base,
      title: "Scenario Weights from Run",
      data: { values: bundle.valuation.scenarioWeights },
      mark: { type: "bar", cornerRadiusTopLeft: 6, cornerRadiusTopRight: 6 },
      encoding: {
        x: {
          field: "scenario",
          type: "nominal",
          sort: ["Pess", "Base", "Opt"],
          axis: { title: null },
        },
        y: { field: "weightPct", type: "quantitative", axis: { title: "Weight (%)" } },
        color: {
          field: "scenario",
          scale: {
            domain: ["Pess", "Base", "Opt"],
            range: [colors.orange, colors.blue, colors.teal],
          },
        },
      },
    },
    scenario_gap_vs_market: {
      ...base,
      title: "Scenario Discount/Premium vs Market",
      data: { values: bundle.valuation.scenarios },
      mark: { type: "bar", cornerRadiusEnd: 6 },
      encoding: {
        y: {
          field: "scenario",
          type: "ordinal",
          sort: ["Pess", "Base", "Opt", "Weighted"],
          axis: { title: null },
        },
        x: {
          field: "gapVsMarketPct",
          type: "quantitative",
          axis: { title: "Discount / Premium (%)" },
        },
        color: {
          condition: { test: "datum.gapVsMarketPct >= 0", value: colors.green },
          value: colors.red,
        },
      },
    },
    comps_ev_ebit: {
      ...base,
      title: "Peer Comps EV/EBIT",
      layer: [
        {
          data: { values: bundle.peers.rows },
          mark: { type: "bar", cornerRadiusEnd: 6 },
          encoding: {
            y: { field: "Ticker", type: "ordinal", sort: "-x", axis: { title: null } },
            x: { field: "EV/EBIT", type: "quantitative", axis: { title: "EV/EBIT (x)" } },
            color: {
              condition: { test: "datum.Ticker === 'MCD'", value: colors.navy },
              value: "#8a9bb0",
            },
          },
        },
        {
          data: { values: [{ median: bundle.peers.evEbitMedian }] },
          mark: { type: "rule", strokeDash: [8, 6], color: colors.blue, strokeWidth: 3 },
          encoding: { x: { field: "median", type: "quantitative" } },
        },
      ],
    },
    comps_ev_sales: {
      ...base,
      title: "Peer Comps EV/Sales",
      layer: [
        {
          data: { values: bundle.peers.rows },
          mark: { type: "bar", cornerRadiusEnd: 6 },
          encoding: {
            y: { field: "Ticker", type: "ordinal", sort: "-x", axis: { title: null } },
            x: { field: "EV/Sales", type: "quantitative", axis: { title: "EV/Sales (x)" } },
            color: {
              condition: { test: "datum.Ticker === 'MCD'", value: colors.navy },
              value: "#8a9bb0",
            },
          },
        },
        {
          data: { values: [{ median: bundle.peers.evSalesMedian }] },
          mark: { type: "rule", strokeDash: [8, 6], color: colors.blue, strokeWidth: 3 },
          encoding: { x: { field: "median", type: "quantitative" } },
        },
      ],
    },
    sensitivity_heatmap: {
      ...base,
      title: "Sensitivity Grid (Value/share)",
      data: { values: bundle.sensitivity.grid },
      layer: [
        {
          mark: { type: "rect", stroke: "#ffffff", strokeWidth: 1.5, cornerRadius: 4 },
          encoding: {
            x: {
              field: "terminalGPct",
              type: "ordinal",
              axis: { title: "Terminal g (%)" },
            },
            y: {
              field: "waccPct",
              type: "ordinal",
              sort: "descending",
              axis: { title: "WACC (%)" },
            },
            color: {
              field: "valuePsUsd",
              type: "quantitative",
              scale: {
                range: ["#fdf3e1", "#f5be62", "#d67a1b", "#8e3f0f"],
              },
              legend: { title: "Value (USD/share)" },
            },
          },
        },
        {
          mark: {
            type: "text",
            align: "center",
            baseline: "middle",
            color: colors.navy,
            fontSize: 14,
            fontWeight: 700,
          },
          encoding: {
            x: { field: "terminalGPct", type: "ordinal" },
            y: { field: "waccPct", type: "ordinal", sort: "descending" },
            text: { field: "valuePsUsd", type: "quantitative", format: ".0f" },
          },
        },
      ],
    },
  };

  if (!specs[id]) throw new Error(`Unknown Vega chart id: ${id}`);
  return specs[id];
}

function baseEchartsOption(title) {
  return {
    animation: false,
    backgroundColor: "#ffffff",
    title: {
      text: title,
      left: 24,
      top: 16,
      textStyle: {
        color: colors.ink,
        fontSize: echartsFont.title,
        fontWeight: 800,
        fontFamily: "Avenir Next, Segoe UI, Arial, sans-serif",
      },
      subtextStyle: {
        color: colors.muted,
        fontSize: echartsFont.subtitle,
        lineHeight: 20,
      },
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(16,42,67,0.95)",
      borderWidth: 0,
      textStyle: { color: "#f0f4f8", fontSize: echartsFont.tooltip },
    },
    textStyle: { fontFamily: "Avenir Next, Segoe UI, Arial, sans-serif" },
    grid: { left: 140, right: 140, top: 140, bottom: 110, containLabel: true },
  };
}

function echartsTakeaways(bundle) {
  const totalRevenue = bundle.sec.segmentRevenueQ12025.reduce((acc, row) => acc + row.revenueUsdMm, 0);
  const iomRow = bundle.sec.segmentRevenueQ12025.find((row) => row.segment === "IOM");
  const iomShare = (iomRow.revenueUsdMm / totalRevenue) * 100;

  const yoy = bundle.sec.segmentRevenueQ12024.map((q1_2024_row) => {
    const q1_2025_row = bundle.sec.segmentRevenueQ12025.find(
      (candidate) => candidate.segment === q1_2024_row.segment,
    );
    return {
      segment: q1_2024_row.segment,
      yoyPct: ((q1_2025_row.revenueUsdMm / q1_2024_row.revenueUsdMm) - 1) * 100,
    };
  });
  const bestYoy = [...yoy].sort((a, b) => b.yoyPct - a.yoyPct)[0];

  const ownershipFranchised = bundle.sec.ownershipCountsQ12025.find(
    (row) => row.ownershipType === "Franchised",
  );
  const ownershipShare = (ownershipFranchised.restaurantCount / bundle.sec.ownershipTotal) * 100;

  const weighted = bundle.valuation.scenarios.find((row) => row.scenario === "Weighted");
  const base = bundle.valuation.scenarios.find((row) => row.scenario === "Base");
  const opt = bundle.valuation.scenarios.find((row) => row.scenario === "Opt");
  const baseWeight = bundle.valuation.scenarioWeights.find((row) => row.scenario === "Base");

  const mcdPeer = bundle.peers.rows.find((row) => row.Ticker === "MCD");
  const mcdEbitPremiumPct = ((mcdPeer["EV/EBIT"] / bundle.peers.evEbitMedian) - 1) * 100;
  const mcdSalesPremiumPct = ((mcdPeer["EV/Sales"] / bundle.peers.evSalesMedian) - 1) * 100;

  const sensitivityValues = bundle.sensitivity.grid.map((row) => row.valuePsUsd);
  const sensitivityMin = Math.min(...sensitivityValues);
  const sensitivityMax = Math.max(...sensitivityValues);

  return {
    segment_revenue_mix_q1_2025: `Takeaway: IOM contributes ${formatNumber(iomShare, 2)}% of Q1'25 revenue.`,
    segment_revenue_yoy_q1: `Takeaway: ${bestYoy.segment} leads YoY with ${signedPct(bestYoy.yoyPct)} revenue growth.`,
    comp_sales_by_segment: "Takeaway: U.S. and IOM comps are negative; IDL remains positive.",
    ownership_mix_q1_2025: `Takeaway: Franchised stores represent ${formatNumber(ownershipShare, 2)}% of total footprint.`,
    franchise_mix_q1_2025: "Takeaway: Conventional franchise agreements dominate the franchise structure.",
    dcf_outcomes_vs_market: `Takeaway: Weighted value is USD ${formatNumber(weighted.valuePsUsd, 2)} (${signedPct(weighted.gapVsMarketPct)}) vs market.`,
    scenario_weights: `Takeaway: Base case drives valuation at ${formatNumber(baseWeight.weightPct, 2)}% weight.`,
    scenario_gap_vs_market: `Takeaway: Only optimistic case clears market (${signedPct(opt.gapVsMarketPct)}); base is ${signedPct(base.gapVsMarketPct)}.`,
    comps_ev_ebit: `Takeaway: MCD trades at ${formatNumber(mcdPeer["EV/EBIT"], 2)}x EV/EBIT (${signedPct(mcdEbitPremiumPct)}) vs peer median.`,
    comps_ev_sales: `Takeaway: MCD trades at ${formatNumber(mcdPeer["EV/Sales"], 2)}x EV/Sales (${signedPct(mcdSalesPremiumPct)}) vs peer median.`,
    sensitivity_heatmap: `Takeaway: Sensitivity range spans USD ${formatNumber(sensitivityMin, 2)} to USD ${formatNumber(sensitivityMax, 2)} per share.`,
  };
}

function echartsOption(id, bundle) {
  const dcf = bundle.valuation.scenarios;
  const marketPrice = bundle.marketPriceUsd;
  const takeaways = echartsTakeaways(bundle);
  const options = {
    segment_revenue_mix_q1_2025: (() => {
      const total = bundle.sec.segmentRevenueQ12025.reduce((acc, row) => acc + row.revenueUsdMm, 0);
      const option = baseEchartsOption("Revenue Mix by Segment (Q1 2025)");
      option.title.subtext = takeaways.segment_revenue_mix_q1_2025;
      option.legend = {
        orient: "vertical",
        right: 40,
        top: "middle",
        textStyle: { color: colors.ink, fontSize: echartsFont.legend },
      };
      option.series = [
        {
          type: "pie",
          radius: ["40%", "70%"],
          center: ["42%", "58%"],
          itemStyle: { borderColor: "#fff", borderWidth: 3 },
          percentPrecision: 2,
          labelLine: { length: 14, length2: 10 },
          label: {
            color: colors.ink,
            fontSize: echartsFont.dataLabel,
          },
          color: [colors.blue, colors.teal, colors.orange],
          data: bundle.sec.segmentRevenueQ12025.map((row) => {
            const sharePct = (row.revenueUsdMm / total) * 100;
            return {
              name: row.segment,
              value: roundTo(row.revenueUsdMm, 2),
              label: {
                formatter: `${row.segment}\n${formatNumber(row.revenueUsdMm, 2)} mm (${formatNumber(sharePct, 2)}%)`,
              },
            };
          }),
        },
      ];
      option.graphic = [
        {
          type: "text",
          left: "35%",
          top: "52%",
          style: {
            text: `USD ${formatNumber(total, 0)}mm\nTotal`,
            fill: colors.navy,
            font: "700 52px Avenir Next",
            textAlign: "center",
          },
        },
      ];
      return option;
    })(),
    segment_revenue_yoy_q1: (() => {
      const option = baseEchartsOption("Segment Revenue (Q1 2024 vs Q1 2025)");
      option.title.subtext = takeaways.segment_revenue_yoy_q1;
      option.legend = {
        top: 70,
        left: 24,
        textStyle: { color: colors.ink, fontSize: echartsFont.legend },
      };
      option.grid = { left: 100, right: 80, top: 165, bottom: 90, containLabel: true };
      option.xAxis = {
        type: "category",
        data: ["U.S.", "IOM", "IDL"],
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
      };
      option.yAxis = {
        type: "value",
        name: "Revenue (USD mm)",
        nameTextStyle: { color: colors.ink, fontSize: echartsFont.axisName },
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitLine: { lineStyle: { color: "#e7edf5" } },
      };
      option.series = [
        {
          name: "Q1 2024",
          type: "bar",
          barWidth: 46,
          itemStyle: { color: colors.slate },
          label: {
            show: true,
            position: "top",
            color: colors.navy,
            fontSize: echartsFont.dataLabel,
            formatter: "{c}",
          },
          data: bundle.sec.segmentRevenueQ12024.map((r) => roundTo(r.revenueUsdMm, 2)),
        },
        {
          name: "Q1 2025",
          type: "bar",
          barWidth: 46,
          itemStyle: { color: colors.blue },
          label: {
            show: true,
            position: "top",
            color: colors.navy,
            fontSize: echartsFont.dataLabel,
            formatter: "{c}",
          },
          data: bundle.sec.segmentRevenueQ12025.map((r) => roundTo(r.revenueUsdMm, 2)),
        },
      ];
      return option;
    })(),
    comp_sales_by_segment: (() => {
      const option = baseEchartsOption("Comparable Sales by Segment (Q1 2025)");
      option.title.subtext = takeaways.comp_sales_by_segment;
      const values = bundle.sec.compSalesQ12025Pct.map((row) => row.compSalesPct);
      const minValue = Math.floor(Math.min(...values) - 0.5);
      const maxValue = Math.ceil(Math.max(...values) + 0.5);
      option.grid = { left: 170, right: 110, top: 150, bottom: 95, containLabel: true };
      option.xAxis = {
        type: "value",
        name: "Comparable Sales (%)",
        min: minValue,
        max: maxValue,
        nameLocation: "middle",
        nameGap: 44,
        nameTextStyle: { color: colors.ink, fontSize: echartsFont.axisName },
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitLine: { lineStyle: { color: "#e7edf5" } },
      };
      option.yAxis = {
        type: "category",
        data: ["U.S.", "IOM", "IDL"],
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
      };
      option.series = [
        {
          type: "bar",
          barWidth: 44,
          data: bundle.sec.compSalesQ12025Pct.map((row) => ({
            value: roundTo(row.compSalesPct, 2),
            itemStyle: {
              color: row.compSalesPct >= 0 ? colors.green : colors.red,
            },
            label: {
              show: true,
              position: row.compSalesPct >= 0 ? "right" : "insideLeft",
              formatter: `${formatNumber(row.compSalesPct, 2)}%`,
              color: row.compSalesPct >= 0 ? colors.navy : "#ffffff",
              fontWeight: 700,
              fontSize: echartsFont.dataLabel,
            },
          })),
          markLine: {
            symbol: "none",
            lineStyle: { color: "#93a2b8", width: 1.5 },
            data: [{ xAxis: 0 }],
          },
        },
      ];
      return option;
    })(),
    ownership_mix_q1_2025: (() => {
      const total = bundle.sec.ownershipTotal;
      const option = baseEchartsOption("Restaurant Ownership Mix (Q1 2025)");
      option.title.subtext = takeaways.ownership_mix_q1_2025;
      option.legend = {
        orient: "vertical",
        right: 40,
        top: "middle",
        textStyle: { color: colors.ink, fontSize: echartsFont.legend },
      };
      option.series = [
        {
          type: "pie",
          radius: ["40%", "70%"],
          center: ["42%", "58%"],
          itemStyle: { borderColor: "#fff", borderWidth: 3 },
          percentPrecision: 2,
          labelLine: { length: 14, length2: 12 },
          label: {
            color: colors.ink,
            fontSize: echartsFont.dataLabel,
          },
          color: [colors.green, "#a3acb8"],
          data: bundle.sec.ownershipCountsQ12025.map((row) => {
            const sharePct = (row.restaurantCount / total) * 100;
            return {
              name: row.ownershipType,
              value: roundTo(row.restaurantCount, 2),
              label: {
                formatter: `${row.ownershipType}\n${formatNumber(row.restaurantCount, 0)} (${formatNumber(sharePct, 2)}%)`,
              },
            };
          }),
        },
      ];
      option.graphic = [
        {
          type: "text",
          left: "35%",
          top: "52%",
          style: {
            text: `${formatNumber(total, 0)}\nRestaurants`,
            fill: colors.navy,
            font: "700 50px Avenir Next",
            textAlign: "center",
          },
        },
      ];
      return option;
    })(),
    franchise_mix_q1_2025: (() => {
      const option = baseEchartsOption("Franchise Type Mix (Q1 2025)");
      option.title.subtext = takeaways.franchise_mix_q1_2025;
      option.legend = {
        orient: "vertical",
        right: 40,
        top: "middle",
        textStyle: { color: colors.ink, fontSize: echartsFont.legend },
      };
      option.series = [
        {
          type: "pie",
          radius: ["40%", "70%"],
          center: ["42%", "58%"],
          itemStyle: { borderColor: "#fff", borderWidth: 3 },
          percentPrecision: 2,
          labelLine: { length: 14, length2: 12 },
          label: {
            color: colors.ink,
            fontSize: echartsFont.dataLabel,
          },
          color: [colors.teal, colors.purple],
          data: bundle.sec.franchiseMixQ12025.map((row) => ({
            name: row.franchiseType,
            value: roundTo(row.sharePct, 2),
            label: {
              formatter: `${row.franchiseType}\n${formatNumber(row.sharePct, 2)}%`,
            },
          })),
        },
      ];
      return option;
    })(),
    dcf_outcomes_vs_market: (() => {
      const option = baseEchartsOption("DCF Outcomes vs Market Price");
      option.title.subtext = takeaways.dcf_outcomes_vs_market;
      const ordered = ["Pess", "Base", "Opt", "Weighted"].map((key) =>
        dcf.find((row) => row.scenario === key),
      );
      const colorMap = {
        Pess: colors.orange,
        Base: colors.blue,
        Opt: colors.teal,
        Weighted: colors.navy,
      };
      option.grid = { left: 100, right: 170, top: 150, bottom: 90, containLabel: true };
      option.xAxis = {
        type: "category",
        data: ordered.map((r) => r.scenario),
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
      };
      option.yAxis = {
        type: "value",
        name: "Value (USD/share)",
        nameTextStyle: { color: colors.ink, fontSize: echartsFont.axisName },
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitLine: { lineStyle: { color: "#e7edf5" } },
      };
      option.series = [
        {
          type: "bar",
          barWidth: 56,
          data: ordered.map((r) => ({
            value: roundTo(r.valuePsUsd, 2),
            itemStyle: { color: colorMap[r.scenario] },
            label: {
              show: true,
              position: "top",
              color: colors.navy,
              fontSize: echartsFont.dataLabel,
              fontWeight: 700,
              formatter: `USD ${formatNumber(r.valuePsUsd, 2)}`,
            },
          })),
          markLine: {
            symbol: "none",
            lineStyle: { color: colors.red, width: 3, type: "dashed" },
            label: {
              position: "insideEndTop",
              formatter: `Market: USD ${formatNumber(marketPrice, 2)}`,
              color: colors.red,
              fontSize: echartsFont.annotation,
              fontWeight: 700,
            },
            data: [{ yAxis: marketPrice }],
          },
        },
      ];
      return option;
    })(),
    scenario_weights: (() => {
      const option = baseEchartsOption("Scenario Weights from Run");
      option.title.subtext = takeaways.scenario_weights;
      const rows = bundle.valuation.scenarioWeights;
      const colorMap = { Pess: colors.orange, Base: colors.blue, Opt: colors.teal };
      option.grid = { left: 100, right: 80, top: 150, bottom: 90, containLabel: true };
      option.xAxis = {
        type: "category",
        data: rows.map((r) => r.scenario),
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
      };
      option.yAxis = {
        type: "value",
        name: "Weight (%)",
        nameTextStyle: { color: colors.ink, fontSize: echartsFont.axisName },
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitLine: { lineStyle: { color: "#e7edf5" } },
      };
      option.series = [
        {
          type: "bar",
          barWidth: 56,
          data: rows.map((r) => ({
            value: roundTo(r.weightPct, 2),
            itemStyle: { color: colorMap[r.scenario] },
            label: {
              show: true,
              position: "top",
              color: colors.navy,
              fontSize: echartsFont.dataLabel,
              fontWeight: 700,
              formatter: `${formatNumber(r.weightPct, 2)}%`,
            },
          })),
        },
      ];
      return option;
    })(),
    scenario_gap_vs_market: (() => {
      const option = baseEchartsOption("Scenario Discount/Premium vs Market");
      option.title.subtext = takeaways.scenario_gap_vs_market;
      const rows = bundle.valuation.scenarios;
      const values = rows.map((r) => r.gapVsMarketPct);
      const minValue = Math.floor(Math.min(...values) - 3);
      const maxValue = Math.ceil(Math.max(...values) + 3);
      option.grid = { left: 170, right: 120, top: 150, bottom: 95, containLabel: true };
      option.yAxis = {
        type: "category",
        data: rows.map((r) => r.scenario),
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
      };
      option.xAxis = {
        type: "value",
        min: minValue,
        max: maxValue,
        name: "Discount / Premium (%)",
        nameLocation: "middle",
        nameGap: 44,
        nameTextStyle: { color: colors.ink, fontSize: echartsFont.axisName },
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitLine: { lineStyle: { color: "#e7edf5" } },
      };
      option.series = [
        {
          type: "bar",
          barWidth: 46,
          data: rows.map((r) => ({
            value: roundTo(r.gapVsMarketPct, 2),
            itemStyle: { color: r.gapVsMarketPct >= 0 ? colors.green : colors.red },
            label: {
              show: true,
              position: r.gapVsMarketPct >= 0 ? "right" : "insideLeft",
              color: r.gapVsMarketPct >= 0 ? colors.navy : "#ffffff",
              fontSize: echartsFont.dataLabel,
              fontWeight: 700,
              formatter: signedPct(r.gapVsMarketPct),
            },
          })),
          markLine: {
            symbol: "none",
            lineStyle: { color: "#93a2b8", width: 1.5 },
            data: [{ xAxis: 0 }],
          },
        },
      ];
      return option;
    })(),
    comps_ev_ebit: (() => {
      const option = baseEchartsOption("Peer Comps EV/EBIT");
      option.title.subtext = takeaways.comps_ev_ebit;
      const rows = [...bundle.peers.rows].sort((a, b) => b["EV/EBIT"] - a["EV/EBIT"]);
      const values = rows.map((row) => row["EV/EBIT"]).sort((a, b) => a - b);
      const maxValue = values[values.length - 1];
      const secondMax = values[values.length - 2] || values[values.length - 1];
      const outlierCapped = maxValue > secondMax * 2;
      const axisMax = outlierCapped
        ? Math.max(45, Math.ceil((secondMax * 1.4) / 5) * 5)
        : Math.ceil((maxValue * 1.12) / 5) * 5;

      option.grid = { left: 170, right: 120, top: 160, bottom: 95, containLabel: true };
      option.yAxis = {
        type: "category",
        data: rows.map((r) => r.Ticker),
        inverse: true,
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
      };
      option.xAxis = {
        type: "value",
        max: axisMax,
        name: "EV/EBIT (x)",
        nameLocation: "middle",
        nameGap: 42,
        nameTextStyle: { color: colors.ink, fontSize: echartsFont.axisName },
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitLine: { lineStyle: { color: "#e7edf5" } },
      };
      option.series = [
        {
          type: "bar",
          barWidth: 44,
          data: rows.map((r) => ({
            value: roundTo(Math.min(r["EV/EBIT"], axisMax), 2),
            itemStyle: {
              color: r.Ticker === "MCD" ? colors.navy : "#8a9bb0",
              borderColor: r["EV/EBIT"] > axisMax ? colors.navy : "transparent",
              borderWidth: r["EV/EBIT"] > axisMax ? 2 : 0,
            },
            label: {
              show: true,
              position: "right",
              color: colors.navy,
              fontSize: echartsFont.dataLabel,
              formatter:
                r["EV/EBIT"] > axisMax
                  ? `${formatNumber(r["EV/EBIT"], 2)}x (outlier)`
                  : `${formatNumber(r["EV/EBIT"], 2)}x`,
            },
          })),
          markLine: {
            symbol: "none",
            lineStyle: { color: colors.blue, width: 3, type: "dashed" },
            label: {
              position: "insideEndTop",
              formatter: `Median: ${formatNumber(bundle.peers.evEbitMedian, 2)}x`,
              color: colors.blue,
              fontSize: echartsFont.annotation,
              fontWeight: 700,
            },
            data: [{ xAxis: bundle.peers.evEbitMedian }],
          },
        },
      ];
      if (outlierCapped) {
        option.graphic = [
          {
            type: "text",
            right: 34,
            top: 124,
            style: {
              text: `Note: ${rows[0].Ticker} at ${formatNumber(rows[0]["EV/EBIT"], 2)}x is capped at ${formatNumber(axisMax, 2)}x for readability.`,
              fill: colors.muted,
              font: `500 ${echartsFont.annotation}px Avenir Next`,
            },
          },
        ];
      }
      return option;
    })(),
    comps_ev_sales: (() => {
      const option = baseEchartsOption("Peer Comps EV/Sales");
      option.title.subtext = takeaways.comps_ev_sales;
      const rows = [...bundle.peers.rows].sort((a, b) => b["EV/Sales"] - a["EV/Sales"]);
      const maxValue = Math.max(...rows.map((row) => row["EV/Sales"]));
      const axisMax = Math.ceil((maxValue * 1.12) / 1) * 1;

      option.grid = { left: 170, right: 120, top: 150, bottom: 95, containLabel: true };
      option.yAxis = {
        type: "category",
        data: rows.map((r) => r.Ticker),
        inverse: true,
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
      };
      option.xAxis = {
        type: "value",
        max: axisMax,
        name: "EV/Sales (x)",
        nameLocation: "middle",
        nameGap: 42,
        nameTextStyle: { color: colors.ink, fontSize: echartsFont.axisName },
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitLine: { lineStyle: { color: "#e7edf5" } },
      };
      option.series = [
        {
          type: "bar",
          barWidth: 44,
          data: rows.map((r) => ({
            value: roundTo(r["EV/Sales"], 2),
            itemStyle: { color: r.Ticker === "MCD" ? colors.navy : "#8a9bb0" },
            label: {
              show: true,
              position: "right",
              color: colors.navy,
              fontSize: echartsFont.dataLabel,
              formatter: `${formatNumber(r["EV/Sales"], 2)}x`,
            },
          })),
          markLine: {
            symbol: "none",
            lineStyle: { color: colors.blue, width: 3, type: "dashed" },
            label: {
              position: "insideEndTop",
              formatter: `Median: ${formatNumber(bundle.peers.evSalesMedian, 2)}x`,
              color: colors.blue,
              fontSize: echartsFont.annotation,
              fontWeight: 700,
            },
            data: [{ xAxis: bundle.peers.evSalesMedian }],
          },
        },
      ];
      return option;
    })(),
    sensitivity_heatmap: (() => {
      const option = baseEchartsOption("Sensitivity Grid (Value/share)");
      option.title.subtext = takeaways.sensitivity_heatmap;
      const xCats = bundle.sensitivity.terminalGVectorPct.map((v) => formatNumber(v, 2));
      const yCats = bundle.sensitivity.waccVectorPct.map((v) => formatNumber(v, 2));
      const values = bundle.sensitivity.grid.map((row) => {
        const chartValue = roundTo(row.valuePsUsd, 2);
        return {
          value: [
            xCats.indexOf(formatNumber(row.terminalGPct, 2)),
            yCats.indexOf(formatNumber(row.waccPct, 2)),
            chartValue,
          ],
          label: { formatter: `${formatNumber(chartValue, 2)}` },
        };
      });

      option.grid = { left: 160, right: 210, top: 160, bottom: 120, containLabel: true };
      option.xAxis = {
        type: "category",
        data: xCats,
        name: "Terminal g (%)",
        nameLocation: "middle",
        nameGap: 40,
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitArea: { show: true },
      };
      option.yAxis = {
        type: "category",
        data: yCats,
        name: "WACC (%)",
        nameLocation: "middle",
        nameGap: 48,
        axisLabel: { color: colors.ink, fontSize: echartsFont.axisLabel },
        splitArea: { show: true },
      };
      option.visualMap = {
        min: Math.min(...bundle.sensitivity.grid.map((row) => row.valuePsUsd)),
        max: Math.max(...bundle.sensitivity.grid.map((row) => row.valuePsUsd)),
        calculable: false,
        orient: "vertical",
        right: 60,
        top: "middle",
        textStyle: { color: colors.ink, fontSize: echartsFont.axisLabel },
        inRange: { color: ["#fdf3e1", "#f5be62", "#d67a1b", "#8e3f0f"] },
      };
      option.series = [
        {
          type: "heatmap",
          data: values,
          label: {
            show: true,
            color: colors.navy,
            fontSize: echartsFont.dataLabel,
            fontWeight: 700,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 8,
              shadowColor: "rgba(0,0,0,0.25)",
            },
          },
        },
      ];
      return option;
    })(),
  };

  if (!options[id]) throw new Error(`Unknown ECharts id: ${id}`);
  return options[id];
}

function renderShellHtml({ chartTitle, libraryLabel, bundle }) {
  const subtitle = [
    `${chartTitle}`,
    `Run ${bundle.meta.runId}`,
    `Ticker ${bundle.meta.ticker}`,
    `Market USD ${formatNumber(bundle.marketPriceUsd, 2)}`,
  ].join(" | ");
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${chartTitle}</title>
  <style>
    :root {
      --bg: ${colors.bg};
      --ink: ${colors.ink};
      --muted: ${colors.muted};
      --card: #ffffff;
      --stroke: #d4deea;
    }
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background: var(--bg);
      overflow: hidden;
      font-family: "Avenir Next", "Segoe UI", Arial, sans-serif;
    }
    .frame {
      width: 1920px;
      height: 1080px;
      box-sizing: border-box;
      padding: 20px 24px;
      background: radial-gradient(circle at 10% 0%, #f8fbff 0%, var(--bg) 55%);
    }
    .title {
      margin: 0;
      color: var(--ink);
      font-size: 44px;
      font-weight: 800;
      letter-spacing: 0.2px;
      line-height: 1.08;
    }
    .sub {
      margin-top: 6px;
      color: var(--muted);
      font-size: 20px;
      line-height: 1.3;
    }
    .card {
      margin-top: 12px;
      height: 976px;
      background: var(--card);
      border: 1px solid var(--stroke);
      border-radius: 14px;
      box-shadow: 0 6px 20px rgba(16, 42, 67, 0.08);
      overflow: hidden;
      position: relative;
    }
    #chart {
      width: 100%;
      height: 100%;
    }
    #status {
      position: absolute;
      right: 14px;
      bottom: 10px;
      font-size: 12px;
      color: #8ea1b9;
      letter-spacing: 0.2px;
      display: none;
    }
    .lib-tag {
      position: absolute;
      right: 14px;
      top: 10px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
  </style>
</head>
<body>
  <main class="frame">
    <h1 class="title">MCD Investment Infographic</h1>
    <div class="sub">${subtitle}</div>
    <section class="card">
      <div class="lib-tag">${libraryLabel}</div>
      <div id="chart"></div>
      <div id="status">render:pending</div>
    </section>
  </main>
</body>
</html>`;
}

async function renderVegaChart({ context, chart, bundle, paths }) {
  const page = await context.newPage();
  await page.setContent(
    renderShellHtml({
      chartTitle: chart.title,
      libraryLabel: "Vega-Lite",
      bundle,
    }),
  );
  await page.addScriptTag({ path: paths.vega });
  await page.addScriptTag({ path: paths.vegaLite });
  await page.addScriptTag({ path: paths.vegaEmbed });

  const spec = vegaSpec(chart.id, bundle);
  await page.evaluate(async ({ chartSpec }) => {
    window.__renderDone = false;
    try {
      const result = await vegaEmbed("#chart", chartSpec, {
        actions: false,
        renderer: "svg",
      });
      if (result && result.view) {
        await result.view.runAsync();
      }
      document.getElementById("status").textContent = "render:ok";
      window.__renderDone = true;
    } catch (error) {
      document.getElementById("status").textContent = `render:error ${String(error)}`;
      throw error;
    }
  }, { chartSpec: spec });

  await page.waitForFunction(() => window.__renderDone === true, { timeout: 30000 });
  const outPath = path.resolve(outPngVega, `${chart.id}.png`);
  await page.screenshot({ path: outPath, fullPage: false });
  await page.close();
}

async function renderEchartsChart({ context, chart, bundle, paths }) {
  const page = await context.newPage();
  await page.setContent(
    renderShellHtml({
      chartTitle: chart.title,
      libraryLabel: "ECharts",
      bundle,
    }),
  );
  await page.addScriptTag({ path: paths.echarts });
  const option = echartsOption(chart.id, bundle);

  await page.evaluate(async ({ chartOption }) => {
    window.__renderDone = false;
    try {
      const chart = echarts.init(document.getElementById("chart"), null, { renderer: "svg" });
      chart.setOption(chartOption, true);
      document.getElementById("status").textContent = "render:ok";
      window.__renderDone = true;
    } catch (error) {
      document.getElementById("status").textContent = `render:error ${String(error)}`;
      throw error;
    }
  }, { chartOption: option });

  await page.waitForFunction(() => window.__renderDone === true, { timeout: 30000 });
  const outPath = path.resolve(outPngEcharts, `${chart.id}.png`);
  await page.screenshot({ path: outPath, fullPage: false });
  await page.close();
}

function writeSources(bundle) {
  const lines = [];
  lines.push(`# MCD Client-Ready Infographic Sources (${bundle.meta.generatedAtUtc})`);
  lines.push("");
  lines.push("## Run artifacts");
  lines.push(`- Run log: \`${bundle.artifacts.runLogPath}\``);
  lines.push(`- Tool calls: \`${bundle.artifacts.toolCallsPath}\``);
  lines.push(`- Canonical dataset: \`${bundle.artifacts.canonicalDatasetPath}\``);
  lines.push("");
  lines.push("## External sources used");
  lines.push(`- SEC 10-Q filing: ${bundle.artifacts.secFilingUrl}`);
  lines.push(`- SEC filing mirror: ${bundle.artifacts.secReportMirror}`);
  lines.push("");
  lines.push("## Key values used");
  lines.push(`- Market price (USD/share): ${formatNumber(bundle.marketPriceUsd, 2)}`);
  lines.push(
    `- DCF outputs (USD/share): ${bundle.valuation.scenarios
      .map((r) => `${r.scenario}=${formatNumber(r.valuePsUsd, 2)}`)
      .join(", ")}`,
  );
  lines.push(
    `- Scenario weights (%): ${bundle.valuation.scenarioWeights
      .map((r) => `${r.scenario}=${formatNumber(r.weightPct, 1)}`)
      .join(", ")}`,
  );
  lines.push(
    `- Sensitivity grid size: ${bundle.sensitivity.waccVectorPct.length}x${bundle.sensitivity.terminalGVectorPct.length}`,
  );
  lines.push("");
  lines.push("## Canonical citations");
  for (const citation of bundle.artifacts.canonicalCitations) {
    lines.push(
      `- ${citation.source} | ${citation.endpoint} | ${citation.url} | accessed=${citation.accessed_at_utc}`,
    );
  }
  lines.push("");
  writeFileSync(path.resolve(outRoot, "sources.md"), lines.join("\n"), "utf-8");
}

function writeComparisonMarkdown(bundle) {
  const lines = [];
  lines.push("# MCD Infographic Comparison (Vega-Lite vs ECharts)");
  lines.push("");
  lines.push(`- Run: \`${bundle.meta.runId}\``);
  lines.push("- Canvas: `1920x1080`");
  lines.push("- Purpose: side-by-side IB-style visual comparison");
  lines.push("");
  lines.push("| Chart | Vega-Lite | ECharts |");
  lines.push("|---|---|---|");
  for (const chart of charts) {
    lines.push(
      `| ${chart.title} | ![](png/vega_lite/${chart.id}.png) | ![](png/echarts/${chart.id}.png) |`,
    );
  }
  lines.push("");
  writeFileSync(path.resolve(outRoot, "comparison.md"), lines.join("\n"), "utf-8");
}

function writeBundle(bundle) {
  writeFileSync(path.resolve(outRoot, "bundle.json"), JSON.stringify(bundle, null, 2), "utf-8");
}

async function main() {
  mkdirSync(outPngVega, { recursive: true });
  mkdirSync(outPngEcharts, { recursive: true });

  const bundle = buildBundle();
  writeBundle(bundle);
  writeSources(bundle);
  writeComparisonMarkdown(bundle);

  const paths = {
    vega: path.resolve(infographicRoot, "node_modules/vega/build/vega.min.js"),
    vegaLite: path.resolve(
      infographicRoot,
      "node_modules/vega-lite/build/vega-lite.min.js",
    ),
    vegaEmbed: path.resolve(
      infographicRoot,
      "node_modules/vega-embed/build/vega-embed.min.js",
    ),
    echarts: path.resolve(infographicRoot, "node_modules/echarts/dist/echarts.min.js"),
  };

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
  });

  try {
    for (const chart of charts) {
      await renderVegaChart({ context, chart, bundle, paths });
      await renderEchartsChart({ context, chart, bundle, paths });
      console.log(`Rendered ${chart.id}`);
    }
  } finally {
    await context.close();
    await browser.close();
  }

  console.log(`Wrote: ${path.relative(repoRoot, outRoot)}`);
  console.log(`Vega PNGs: ${charts.length}`);
  console.log(`ECharts PNGs: ${charts.length}`);
}

await main();
