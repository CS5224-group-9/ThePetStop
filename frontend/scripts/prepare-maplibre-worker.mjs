import { copyFile, mkdir, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const packagePath = require.resolve("maplibre-gl/package.json");
const { version } = JSON.parse(await readFile(packagePath, "utf8"));
const packageRoot = dirname(packagePath);
const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const destination = join(frontendRoot, "public", "maplibre", version);
await mkdir(destination, { recursive: true });
await copyFile(
  join(packageRoot, "dist", "maplibre-gl-worker.mjs"),
  join(destination, "maplibre-gl-worker.mjs"),
);
await copyFile(
  join(packageRoot, "LICENSE.txt"),
  join(destination, "LICENSE.txt"),
);
console.log(`Prepared local MapLibre ${version} worker.`);
