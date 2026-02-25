import { mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const inputHtml = args["input-html"];
  const outputPdf = args["output-pdf"];
  if (!inputHtml || !outputPdf) {
    throw new Error(
      "Usage: node render_pdf_from_html.mjs --input-html <memo.html> --output-pdf <memo.pdf>",
    );
  }

  mkdirSync(path.dirname(outputPdf), { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 1000 },
    deviceScaleFactor: 1,
  });

  try {
    const page = await context.newPage();
    await page.goto(pathToFileURL(path.resolve(inputHtml)).href, {
      waitUntil: "networkidle",
      timeout: 60000,
    });
    await page.emulateMedia({ media: "screen" });
    await page.pdf({
      path: path.resolve(outputPdf),
      format: "A4",
      printBackground: true,
      margin: {
        top: "8mm",
        right: "8mm",
        bottom: "8mm",
        left: "8mm",
      },
    });
  } finally {
    await context.close();
    await browser.close();
  }

  console.log(`PDF written: ${outputPdf}`);
}

await main();
