import { readFile } from "node:fs/promises";

const catalogPath = new URL("../realeyesvr/website/data/resources.json", import.meta.url);
const catalog = JSON.parse(await readFile(catalogPath, "utf8"));
const failures = [];

for (const resource of catalog.resources) {
  try {
    let response = await fetch(resource.url, {
      method: "HEAD",
      redirect: "follow",
      signal: AbortSignal.timeout(15000),
      headers: { "User-Agent": "RealEyesVR-Link-Checker/1.0" }
    });

    if (response.status === 403 || response.status === 405) {
      response = await fetch(resource.url, {
        method: "GET",
        redirect: "follow",
        signal: AbortSignal.timeout(15000),
        headers: { "User-Agent": "RealEyesVR-Link-Checker/1.0", Range: "bytes=0-1024" }
      });
    }

    const okay = response.status >= 200 && response.status < 400;
    console.log(`${okay ? "OK" : "FAIL"} ${response.status} ${resource.name} — ${resource.url}`);
    if (!okay) failures.push(`${resource.name}: HTTP ${response.status}`);
  } catch (error) {
    console.error(`FAIL ${resource.name} — ${error.message}`);
    failures.push(`${resource.name}: ${error.message}`);
  }
}

if (failures.length) {
  console.error(`\n${failures.length} resource link(s) need review.`);
  process.exitCode = 1;
} else {
  console.log(`\nAll ${catalog.resources.length} resource links responded.`);
}
