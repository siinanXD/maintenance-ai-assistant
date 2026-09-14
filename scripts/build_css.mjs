import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const ROOT_DIR = dirname(dirname(fileURLToPath(import.meta.url)));
const SOURCE_DIR = join(ROOT_DIR, "app", "static", "css", "src");
const GENERATED_DIR = join(ROOT_DIR, "tmp", "css-build");
const GENERATED_INPUT = join(GENERATED_DIR, "input.css");
const OUTPUT_CSS = join(ROOT_DIR, "app", "static", "css", "output.css");

/**
 * Return all CSS sources in cascade order: folders and files sorted by path
 * (00-foundation, 10-legacy, 20-components, 90-overrides).
 *
 * @param {string} directory Directory to scan.
 * @returns {string[]} Sorted CSS source paths.
 */
function cssSourceFiles(directory = SOURCE_DIR) {
  return readdirSync(directory, { withFileTypes: true })
    .sort((first, second) => first.name.localeCompare(second.name))
    .flatMap((entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) return cssSourceFiles(path);
      return entry.name.endsWith(".css") ? [path] : [];
    });
}

/**
 * Build the temporary Tailwind input file from split source parts.
 *
 * @returns {void}
 */
function writeGeneratedInput() {
  mkdirSync(GENERATED_DIR, { recursive: true });
  const content = cssSourceFiles()
    .map((path) => readFileSync(path, "utf8").trimEnd())
    .join("\n\n");
  writeFileSync(GENERATED_INPUT, content + "\n", "utf8");
}

/**
 * Run Tailwind against the generated source file.
 *
 * @returns {void}
 */
function runTailwind() {
  const result = spawnSync(
    process.execPath,
    [join(ROOT_DIR, "node_modules", "tailwindcss", "lib", "cli.js"), "-i", GENERATED_INPUT, "-o", OUTPUT_CSS, "--minify"],
    { cwd: ROOT_DIR, stdio: "inherit" }
  );
  if (result.status !== 0) {
    throw new Error("Tailwind CSS build failed.");
  }
}

/**
 * Build the application CSS from split source files.
 *
 * @returns {void}
 */
function main() {
  rmSync(GENERATED_DIR, { recursive: true, force: true });
  writeGeneratedInput();
  runTailwind();
}

main();
