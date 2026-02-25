import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const outDir = path.resolve(root, "..", "artifacts", "infographics", "env_smoke");

mkdirSync(outDir, { recursive: true });

const vegaPath = path.resolve(root, "node_modules", "vega", "build", "vega.min.js");
const vegaLitePath = path.resolve(
  root,
  "node_modules",
  "vega-lite",
  "build",
  "vega-lite.min.js",
);
const vegaEmbedPath = path.resolve(
  root,
  "node_modules",
  "vega-embed",
  "build",
  "vega-embed.min.js",
);
const echartsPath = path.resolve(
  root,
  "node_modules",
  "echarts",
  "dist",
  "echarts.min.js",
);

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.setContent(
  `
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { margin: 0; background: #f4f7fb; font-family: "Avenir Next", "Segoe UI", Arial, sans-serif; }
    .wrap { padding: 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    .card { background: #fff; border: 1px solid #d6deea; border-radius: 12px; padding: 12px; height: 780px; }
    .title { font-size: 24px; font-weight: 800; color: #102a43; margin: 8px 0 14px; }
    #vega, #echarts { width: 100%; height: 700px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="title">Vega-Lite Smoke</div>
      <div id="vega"></div>
    </div>
    <div class="card">
      <div class="title">ECharts Smoke</div>
      <div id="echarts"></div>
    </div>
  </div>
</body>
</html>
`,
);

await page.addScriptTag({ path: vegaPath });
await page.addScriptTag({ path: vegaLitePath });
await page.addScriptTag({ path: vegaEmbedPath });
await page.addScriptTag({ path: echartsPath });

await page.evaluate(async () => {
  const vegaSpec = {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    data: { values: [
      { scenario: "Pess", value: 109.4 },
      { scenario: "Base", value: 247.3 },
      { scenario: "Opt", value: 425.3 },
      { scenario: "Weighted", value: 239.5 }
    ] },
    mark: { type: "bar", cornerRadiusTopLeft: 5, cornerRadiusTopRight: 5 },
    width: 600,
    height: 600,
    encoding: {
      x: { field: "scenario", type: "nominal" },
      y: { field: "value", type: "quantitative", title: "USD/share" },
      color: {
        field: "scenario",
        scale: { range: ["#d97706", "#2f6cad", "#1f8a70", "#153251"] },
        legend: null
      }
    },
    config: {
      axis: { labelColor: "#334e68", titleColor: "#102a43" },
      background: "#ffffff"
    }
  };
  await vegaEmbed("#vega", vegaSpec, { actions: false });

  const chart = echarts.init(document.getElementById("echarts"), null, { renderer: "canvas" });
  chart.setOption({
    animation: false,
    backgroundColor: "#ffffff",
    xAxis: { type: "category", data: ["Pess", "Base", "Opt", "Weighted"] },
    yAxis: { type: "value", name: "USD/share" },
    series: [
      {
        type: "bar",
        data: [
          { value: 109.4, itemStyle: { color: "#d97706" } },
          { value: 247.3, itemStyle: { color: "#2f6cad" } },
          { value: 425.3, itemStyle: { color: "#1f8a70" } },
          { value: 239.5, itemStyle: { color: "#153251" } }
        ]
      }
    ]
  });
});

await page.screenshot({ path: path.join(outDir, "vega_echarts_smoke.png"), fullPage: true });
await browser.close();

writeFileSync(
  path.join(outDir, "README.txt"),
  [
    "Smoke render completed.",
    "Output: vega_echarts_smoke.png",
    "Purpose: verifies Vega-Lite + ECharts + Playwright rendering path."
  ].join("\n"),
  "utf-8",
);

console.log(`Wrote ${path.join(outDir, "vega_echarts_smoke.png")}`);
