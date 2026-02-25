import { mkdirSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..", "..");

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
  card: "#ffffff",
  stroke: "#d4deea",
};

const font = {
  shellTitle: 28,
  shellSubtitle: 18,
  title: 26,
  subtitle: 15,
  axis: 14,
  axisName: 15,
  legend: 14,
  label: 14,
  annotation: 13,
};

const RENDER_PROFILES = {
  memo: {
    width: 1600,
    height: 900,
    deviceScaleFactor: 1.5,
    showShell: false,
  },
  showcase: {
    width: 1920,
    height: 1080,
    deviceScaleFactor: 2,
    showShell: true,
  },
};

const CHART_META = {
  dcf_outcomes_vs_market: "DCF Outcomes vs Market Price (USD/share)",
  scenario_weights: "Scenario Weights from Run (%)",
  scenario_gap_vs_market: "Scenario Discount/Premium vs Market (%)",
  comps_ev_ebit: "Peer Comps EV/EBIT (x)",
  comps_ev_sales: "Peer Comps EV/Sales (x)",
  sensitivity_heatmap: "Sensitivity Grid (Value/share by WACC x g)",
  peer_market_cap: "Peer Market Cap Snapshot (USD bn)",
  peer_revenue_ebit: "Peer Revenue vs EBIT Margin",
};

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const value = argv[i + 1];
    if (!value || value.startsWith("--")) {
      args[key] = "true";
      continue;
    }
    args[key] = value;
    i += 1;
  }
  return args;
}

function purgeStaleOutputs(outDir) {
  const entries = readdirSync(outDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    if (!entry.name.endsWith(".png") && entry.name !== "chart_manifest.json") continue;
    unlinkSync(path.resolve(outDir, entry.name));
  }
}

function number(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "N/A";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function signedPct(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "N/A";
  return `${n > 0 ? "+" : ""}${number(n, digits)}%`;
}

function round(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return NaN;
  const factor = 10 ** digits;
  return Math.round(n * factor) / factor;
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function requireFiniteRows(rows, key, minimum) {
  const valid = rows.filter((row) => {
    const v = finiteNumber(row[key]);
    return v !== null && v > 0;
  });
  if (valid.length < minimum) {
    throw new Error(`Insufficient valid rows for ${key}: got=${valid.length}, required>=${minimum}`);
  }
  return valid;
}

function baseOption(title, takeaway) {
  return {
    animation: false,
    backgroundColor: colors.card,
    title: {
      text: title,
      left: 24,
      top: 16,
      textStyle: {
        color: colors.ink,
        fontSize: font.title,
        fontWeight: 800,
        fontFamily: "Avenir Next, Segoe UI, Arial, sans-serif",
      },
      subtext: takeaway || "",
      subtextStyle: {
        color: colors.muted,
        fontSize: font.subtitle,
        lineHeight: 24,
      },
    },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(16,42,67,0.95)",
      borderWidth: 0,
      textStyle: { color: "#f0f4f8", fontSize: 15 },
      confine: true,
    },
    textStyle: {
      color: colors.ink,
      fontFamily: "Avenir Next, Segoe UI, Arial, sans-serif",
    },
    grid: {
      left: 150,
      right: 130,
      top: 165,
      bottom: 95,
      containLabel: true,
    },
  };
}

function chartOption(id, bundle) {
  const takeaways = bundle.chart_takeaways || {};
  const title = CHART_META[id] || id;
  const scenarioRows = (bundle.valuation && bundle.valuation.scenarios) || [];
  const peersRows = (bundle.peers && bundle.peers.rows) || [];
  const sensitivity = bundle.sensitivity || {};

  if (id === "dcf_outcomes_vs_market") {
    const market = finiteNumber(bundle.marketPriceUsd);
    const ordered = ["Pess", "Base", "Opt", "Weighted"].map((name) =>
      scenarioRows.find((row) => row.scenario === name),
    );
    const colorBy = {
      Pess: colors.orange,
      Base: colors.blue,
      Opt: colors.teal,
      Weighted: colors.navy,
    };
    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 110, right: 170, top: 160, bottom: 95, containLabel: true };
    option.xAxis = {
      type: "category",
      data: ordered.map((row) => row && row.scenario ? row.scenario : "N/A"),
      axisLabel: { color: colors.ink, fontSize: font.axis },
    };
    option.yAxis = {
      type: "value",
      name: "Value (USD/share)",
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.series = [
      {
        type: "bar",
        barWidth: 58,
        data: ordered.map((row) => {
          const value = row ? finiteNumber(row.valuePsUsd) : null;
          const scenario = row ? row.scenario : "Base";
          return {
            value: value ?? NaN,
            itemStyle: { color: colorBy[scenario] || colors.slate },
            label: {
              show: value !== null,
              position: "top",
              color: colors.navy,
              fontSize: font.label,
              fontWeight: 700,
              formatter: `USD ${number(value)}`,
            },
          };
        }),
      },
    ];
    if (market !== null) {
      option.series[0].markLine = {
        symbol: "none",
        lineStyle: { color: colors.red, width: 2.5, type: "dashed" },
        label: {
          position: "insideEndTop",
          formatter: `Market: USD ${number(market)}`,
          color: colors.red,
          fontSize: font.annotation,
          fontWeight: 700,
        },
        data: [{ yAxis: market }],
      };
    }
    return option;
  }

  if (id === "scenario_weights") {
    const rows = scenarioRows.filter((row) => ["Pess", "Base", "Opt"].includes(row.scenario));
    const colorBy = { Pess: colors.orange, Base: colors.blue, Opt: colors.teal };
    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 110, right: 80, top: 160, bottom: 95, containLabel: true };
    option.xAxis = {
      type: "category",
      data: rows.map((row) => row.scenario),
      axisLabel: { color: colors.ink, fontSize: font.axis },
    };
    option.yAxis = {
      type: "value",
      name: "Weight (%)",
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.series = [
      {
        type: "bar",
        barWidth: 58,
        data: rows.map((row) => {
          const value = finiteNumber(row.weightPct);
          return {
            value: value ?? NaN,
          itemStyle: { color: colorBy[row.scenario] || colors.slate },
          label: {
              show: value !== null,
            position: "top",
            color: colors.navy,
            fontWeight: 700,
            fontSize: font.label,
              formatter: `${number(value)}%`,
          },
          };
        }),
      },
    ];
    return option;
  }

  if (id === "scenario_gap_vs_market") {
    const rows = ["Weighted", "Opt", "Base", "Pess"]
      .map((name) => scenarioRows.find((row) => row.scenario === name))
      .filter(Boolean);
    const values = rows
      .map((row) => finiteNumber(row.gapVsMarketPct))
      .filter((v) => v !== null);
    const min = values.length ? Math.floor(Math.min(...values) - 4) : -20;
    const max = values.length ? Math.ceil(Math.max(...values) + 4) : 20;

    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 185, right: 120, top: 160, bottom: 100, containLabel: true };
    option.yAxis = {
      type: "category",
      data: rows.map((row) => row.scenario),
      axisLabel: { color: colors.ink, fontSize: font.axis },
    };
    option.xAxis = {
      type: "value",
      min,
      max,
      name: "Discount / Premium (%)",
      nameLocation: "middle",
      nameGap: 44,
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.series = [
      {
        type: "bar",
        barWidth: 46,
        data: rows.map((row) => {
          const value = finiteNumber(row.gapVsMarketPct);
          return {
            value: value ?? NaN,
            itemStyle: { color: (value ?? 0) >= 0 ? colors.green : colors.red },
            label: {
              show: value !== null,
              position: (value ?? 0) >= 0 ? "right" : "insideLeft",
              color: (value ?? 0) >= 0 ? colors.navy : "#ffffff",
              fontWeight: 700,
              fontSize: font.label,
              formatter: signedPct(value),
            },
          };
        }),
        markLine: {
          symbol: "none",
          lineStyle: { color: "#93a2b8", width: 1.5 },
          data: [{ xAxis: 0 }],
        },
      },
    ];
    return option;
  }

  if (id === "comps_ev_ebit") {
    const validRows = requireFiniteRows(peersRows, "EV/EBIT", 3)
      .map((row) => ({ ...row, __value: finiteNumber(row["EV/EBIT"]) }))
      .sort((a, b) => b.__value - a.__value);
    const nmfTickers = peersRows
      .filter((row) => {
        const value = finiteNumber(row["EV/EBIT"]);
        return value === null || value <= 0;
      })
      .map((row) => String(row.Ticker || "N/A"))
      .filter(Boolean);
    const values = validRows.map((row) => row.__value).sort((a, b) => a - b);
    const max = values.length ? values[values.length - 1] : 0;
    const second = values.length > 1 ? values[values.length - 2] : max;
    const outlier = max > second * 2;
    const axisMax = outlier ? Math.max(50, Math.ceil((second * 1.5) / 5) * 5) : Math.ceil((max * 1.15) / 5) * 5;

    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 175, right: 110, top: 160, bottom: 95, containLabel: true };
    option.yAxis = {
      type: "category",
      data: validRows.map((row) => row.Ticker),
      inverse: true,
      axisLabel: { color: colors.ink, fontSize: font.axis },
    };
    option.xAxis = {
      type: "value",
      max: axisMax,
      name: "EV/EBIT (x)",
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.series = [
      {
        type: "bar",
        barWidth: 44,
        data: validRows.map((row) => {
          const raw = row.__value;
          const capped = Math.min(raw, axisMax);
          return {
            value: capped,
            itemStyle: {
              color: row.Ticker === bundle.meta.ticker ? colors.navy : "#8a9bb0",
              borderColor: raw > axisMax ? colors.navy : "transparent",
              borderWidth: raw > axisMax ? 2 : 0,
            },
            label: {
              show: true,
              position: "right",
              color: colors.navy,
              fontSize: font.label,
              formatter: raw > axisMax ? `${number(raw)}x (outlier)` : `${number(raw)}x`,
            },
          };
        }),
        markLine: {
          symbol: "none",
          lineStyle: { color: colors.blue, width: 3, type: "dashed" },
          label: {
            position: "insideEndTop",
            formatter: `Median: ${number(bundle.peers.evEbitMedian)}x`,
            color: colors.blue,
            fontWeight: 700,
            fontSize: font.annotation,
          },
          data: [{ xAxis: finiteNumber(bundle.peers.evEbitMedian) ?? 0 }],
        },
      },
    ];
    const noteLines = [];
    if (outlier && validRows.length) {
      noteLines.push(
        `${validRows[0].Ticker} at ${number(validRows[0]["EV/EBIT"])}x capped at ${number(axisMax)}x.`,
      );
    }
    if (nmfTickers.length > 0) {
      noteLines.push(`Excluded NMF peers: ${nmfTickers.join(", ")}.`);
    }
    if (noteLines.length) {
      option.graphic = [{
        type: "text",
        right: 30,
        top: 124,
        style: {
          text: `Note: ${noteLines.join(" ")}`,
          fill: colors.muted,
          font: `500 ${font.annotation}px Avenir Next`,
        },
      }];
    }
    return option;
  }

  if (id === "comps_ev_sales") {
    const rows = requireFiniteRows(peersRows, "EV/Sales", 3)
      .map((row) => ({ ...row, __value: finiteNumber(row["EV/Sales"]) }))
      .sort((a, b) => b.__value - a.__value);
    const max = Math.max(...rows.map((row) => row.__value), 1);
    const axisMax = Math.ceil(max * 1.15);

    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 175, right: 110, top: 160, bottom: 95, containLabel: true };
    option.yAxis = {
      type: "category",
      data: rows.map((row) => row.Ticker),
      inverse: true,
      axisLabel: { color: colors.ink, fontSize: font.axis },
    };
    option.xAxis = {
      type: "value",
      max: axisMax,
      name: "EV/Sales (x)",
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.series = [
      {
        type: "bar",
        barWidth: 44,
        data: rows.map((row) => {
          const value = row.__value;
          return {
            value,
            itemStyle: { color: row.Ticker === bundle.meta.ticker ? colors.navy : "#8a9bb0" },
            label: {
              show: true,
              position: "right",
              color: colors.navy,
              fontSize: font.label,
              formatter: `${number(value)}x`,
            },
          };
        }),
        markLine: {
          symbol: "none",
          lineStyle: { color: colors.blue, width: 3, type: "dashed" },
          label: {
            position: "insideEndTop",
            formatter: `Median: ${number(bundle.peers.evSalesMedian)}x`,
            color: colors.blue,
            fontWeight: 700,
            fontSize: font.annotation,
          },
          data: [{ xAxis: finiteNumber(bundle.peers.evSalesMedian) ?? 0 }],
        },
      },
    ];
    return option;
  }

  if (id === "sensitivity_heatmap") {
    const xCats = (sensitivity.terminalGVectorPct || []).map((v) => number(v));
    const yCats = (sensitivity.waccVectorPct || []).map((v) => number(v));
    const gridRows = sensitivity.grid || [];
    const values = gridRows
      .map((row) => {
        const x = xCats.indexOf(number(row.terminalGPct));
        const y = yCats.indexOf(number(row.waccPct));
        const value = finiteNumber(row.valuePsUsd);
        if (x < 0 || y < 0 || value === null) {
          return null;
        }
        return {
          value: [x, y, value],
          label: { formatter: number(value) },
        };
      })
      .filter(Boolean);

    if (values.length === 0) {
      throw new Error("No valid values available for sensitivity_heatmap.");
    }

    const numericValues = values.map((row) => row.value[2]).filter((v) => Number.isFinite(v));
    const min = Math.min(...numericValues);
    const max = Math.max(...numericValues);

    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 165, right: 215, top: 170, bottom: 122, containLabel: true };
    option.xAxis = {
      type: "category",
      data: xCats,
      name: "Terminal g (%)",
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitArea: { show: true },
    };
    option.yAxis = {
      type: "category",
      data: yCats,
      name: "WACC (%)",
      nameLocation: "middle",
      nameGap: 50,
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitArea: { show: true },
    };
    option.visualMap = {
      min,
      max,
      calculable: false,
      orient: "vertical",
      right: 65,
      top: "middle",
      textStyle: { color: colors.ink, fontSize: font.axis },
      inRange: { color: ["#fdf3e1", "#f5be62", "#d67a1b", "#8e3f0f"] },
    };
    option.series = [
      {
        type: "heatmap",
        data: values,
        label: {
          show: true,
          color: colors.navy,
          fontSize: font.label,
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
  }

  if (id === "peer_market_cap") {
    const rows = requireFiniteRows(peersRows, "Market Cap ($B)", 3)
      .map((row) => ({ ...row, __value: finiteNumber(row["Market Cap ($B)"]) }))
      .sort((a, b) => b.__value - a.__value);
    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 175, right: 110, top: 160, bottom: 95, containLabel: true };
    option.yAxis = {
      type: "category",
      data: rows.map((row) => row.Ticker),
      inverse: true,
      axisLabel: { color: colors.ink, fontSize: font.axis },
    };
    option.xAxis = {
      type: "value",
      name: "Market Cap (USD bn)",
      nameLocation: "middle",
      nameGap: 42,
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.series = [
      {
        type: "bar",
        barWidth: 44,
        itemStyle: { color: colors.slate },
        data: rows.map((row) => ({
          value: row.__value,
          itemStyle: { color: row.Ticker === bundle.meta.ticker ? colors.navy : colors.slate },
          label: {
            show: true,
            position: "right",
            color: colors.navy,
            fontSize: font.label,
            formatter: `${number(row.__value)} bn`,
          },
        })),
      },
    ];
    return option;
  }

  if (id === "peer_revenue_ebit") {
    const rows = [...peersRows].filter((row) => {
      const rev = finiteNumber(row["Revenue ($B)"]);
      const ebit = finiteNumber(row["EBIT ($B)"]);
      return rev !== null && rev > 0 && ebit !== null;
    });
    if (rows.length < 3) {
      throw new Error(`Insufficient valid rows for peer_revenue_ebit: got=${rows.length}, required>=3`);
    }
    const points = rows.map((row) => {
      const rev = finiteNumber(row["Revenue ($B)"]) ?? 0;
      const ebit = finiteNumber(row["EBIT ($B)"]) ?? 0;
      const margin = (ebit / rev) * 100;
      const marketCap = finiteNumber(row["Market Cap ($B)"]);
      const capForSize = marketCap !== null && marketCap > 0 ? marketCap : 10;
      const symbolSize = Math.max(14, Math.min(56, Math.sqrt(capForSize) * 2.2));
      const ticker = String(row.Ticker || "");
      const isTarget = ticker === bundle.meta.ticker;
      return {
        name: ticker,
        value: [round(rev), round(margin), round(capForSize)],
        symbolSize: round(symbolSize, 1),
        itemStyle: {
          color: isTarget ? colors.navy : colors.blue,
          opacity: 0.85,
        },
      };
    });

    const xValues = points.map((point) => point.value[0]);
    const yValues = points.map((point) => point.value[1]);
    const xMax = Math.max(...xValues);
    const yMin = Math.min(...yValues);
    const yMax = Math.max(...yValues);

    const option = baseOption(title, takeaways[id]);
    option.grid = { left: 120, right: 120, top: 160, bottom: 98, containLabel: true };
    option.xAxis = {
      type: "value",
      min: 0,
      max: Math.ceil(xMax * 1.15),
      name: "Revenue (USD bn)",
      nameLocation: "middle",
      nameGap: 40,
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.yAxis = {
      type: "value",
      min: Math.floor((yMin - 5) / 5) * 5,
      max: Math.ceil((yMax + 5) / 5) * 5,
      name: "EBIT Margin (%)",
      nameTextStyle: { color: colors.ink, fontSize: font.axisName },
      axisLabel: { color: colors.ink, fontSize: font.axis },
      splitLine: { lineStyle: { color: "#e7edf5" } },
    };
    option.series = [
      {
        type: "scatter",
        symbolSize: 26,
        label: {
          show: true,
          formatter: "{b}",
          color: colors.ink,
          fontSize: font.label,
          position: "right",
        },
        labelLayout: { hideOverlap: true },
        data: points,
        tooltip: {
          formatter:
            "{b}<br/>Revenue: USD {@[0]}bn<br/>EBIT Margin: {@[1]}%<br/>Market Cap: USD {@[2]}bn",
        },
      },
    ];
    return option;
  }

  throw new Error(`Unsupported chart id: ${id}`);
}

function renderShellHtml({ ticker, chartTitle, subtitle, profile }) {
  const frameHeader = profile.showShell
    ? `
    <h1 class="title">${ticker} Investment Infographic</h1>
    <div class="sub">${subtitle}</div>
    `
    : "";
  const cardHeight = profile.showShell ? `${profile.height - 104}px` : `${profile.height - 22}px`;

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
      --card: ${colors.card};
      --stroke: ${colors.stroke};
    }
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      background: var(--bg);
      overflow: hidden;
      font-family: "Avenir Next", "Segoe UI", Arial, sans-serif;
    }
    .frame {
      width: ${profile.width}px;
      height: ${profile.height}px;
      box-sizing: border-box;
      padding: 10px 12px;
      background: radial-gradient(circle at 10% 0%, #f8fbff 0%, var(--bg) 55%);
    }
    .title {
      margin: 0;
      color: var(--ink);
      font-size: ${font.shellTitle}px;
      line-height: 1.08;
      font-weight: 800;
      letter-spacing: 0.15px;
    }
    .sub {
      margin-top: 6px;
      color: var(--muted);
      font-size: ${font.shellSubtitle}px;
      line-height: 1.2;
    }
    .card {
      margin-top: ${profile.showShell ? 12 : 0}px;
      height: ${cardHeight};
      background: var(--card);
      border: 1px solid var(--stroke);
      border-radius: ${profile.showShell ? 14 : 8}px;
      box-shadow: ${profile.showShell ? "0 6px 20px rgba(16, 42, 67, 0.08)" : "none"};
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
      display: none;
    }
  </style>
</head>
<body>
  <main class="frame">
    ${frameHeader}
    <section class="card">
      <div id="chart"></div>
      <div id="status">render:pending</div>
    </section>
  </main>
</body>
</html>`;
}

async function renderChart({ context, chartId, bundle, outDir, chartIndex, profile }) {
  const chartTitle = CHART_META[chartId] || chartId;
  const page = await context.newPage();
  const subtitle = [
    chartTitle,
    `Run ${bundle.meta.runId}`,
    `Ticker ${bundle.meta.ticker}`,
    `Status ${bundle.meta.status}`,
    `Market USD ${number(bundle.marketPriceUsd)}`,
  ].join(" | ");

  await page.setContent(
    renderShellHtml({
      ticker: bundle.meta.ticker,
      chartTitle,
      subtitle,
      profile,
    }),
  );
  await page.addScriptTag({
    path: path.resolve(repoRoot, "infographics/node_modules/echarts/dist/echarts.min.js"),
  });

  const option = chartOption(chartId, bundle);
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

  const prefix = String(chartIndex + 1).padStart(2, "0");
  const outputPng = path.resolve(outDir, `${prefix}_${chartId}.png`);
  await page.screenshot({ path: outputPng, fullPage: false });
  await page.close();

  return {
    id: chartId,
    title: chartTitle,
    takeaway: (bundle.chart_takeaways && bundle.chart_takeaways[chartId]) || "",
    png_path: outputPng,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const bundlePath = args.bundle;
  const outDir = args["out-dir"];
  const profile = RENDER_PROFILES[String(args.profile || "memo").trim()] || RENDER_PROFILES.memo;
  if (!bundlePath || !outDir) {
    throw new Error("Usage: node render_run_echarts_pack.mjs --bundle <bundle.json> --out-dir <dir> [--profile memo|showcase]");
  }

  const bundle = JSON.parse(readFileSync(bundlePath, "utf-8"));
  const chartIdsRaw = Array.isArray(bundle.chart_ids) ? bundle.chart_ids : [];
  const chartIds = chartIdsRaw
    .map((item) => String(item || "").trim())
    .filter((item) => item && Object.prototype.hasOwnProperty.call(CHART_META, item));

  if (chartIds.length === 0) {
    throw new Error("Bundle chart_ids is empty after filtering.");
  }

  mkdirSync(outDir, { recursive: true });
  purgeStaleOutputs(outDir);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: profile.width, height: profile.height },
    deviceScaleFactor: profile.deviceScaleFactor,
  });

  const manifestCharts = [];
  const renderErrors = [];
  try {
    for (let i = 0; i < chartIds.length; i += 1) {
      const chartId = chartIds[i];
      try {
        const artifact = await renderChart({
          context,
          chartId,
          bundle,
          outDir,
          chartIndex: i,
          profile,
        });
        manifestCharts.push(artifact);
        console.log(`Rendered ${chartId}`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        renderErrors.push({ id: chartId, error: message });
        console.error(`Render failed for ${chartId}: ${message}`);
      }
    }
  } finally {
    await context.close();
    await browser.close();
  }

  if (manifestCharts.length === 0) {
    throw new Error(`All chart renders failed: ${JSON.stringify(renderErrors)}`);
  }

  const manifest = {
    generated_at_utc: new Date().toISOString(),
    run_id: bundle.meta.runId,
    ticker: bundle.meta.ticker,
    chart_count: manifestCharts.length,
    failed_charts: renderErrors,
    charts: manifestCharts,
  };

  const manifestPath = path.resolve(outDir, "chart_manifest.json");
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");
  console.log(`Chart manifest: ${path.relative(repoRoot, manifestPath)}`);
}

await main();
