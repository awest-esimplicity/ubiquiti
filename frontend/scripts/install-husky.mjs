import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");

try {
  execSync("npx husky install frontend/.husky", {
    cwd: repoRoot,
    stdio: "inherit"
  });
} catch (error) {
  console.warn("Skipping Husky install:", error?.message ?? error);
}
