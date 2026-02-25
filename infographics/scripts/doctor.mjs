import process from "node:process";

const major = Number.parseInt(process.versions.node.split(".")[0], 10);
if (Number.isNaN(major) || major < 20) {
  console.error(`Node ${process.versions.node} detected. Require >=20.11.0.`);
  process.exit(1);
}

const packages = ["vega", "vega-lite", "vega-embed", "echarts", "playwright"];
for (const pkg of packages) {
  try {
    const mod = await import(pkg);
    const v = mod?.version || mod?.default?.version || "ok";
    console.log(`${pkg}: ${v}`);
  } catch (err) {
    console.error(`${pkg}: missing (${err.message})`);
    process.exitCode = 1;
  }
}

if (process.exitCode && process.exitCode !== 0) {
  process.exit(process.exitCode);
}
console.log("Environment doctor: PASS");
