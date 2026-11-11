// Build do painel com esbuild (sem framework de build pesado).
//   node build.mjs              -> dist/ consumindo a API (/api/...)
//   node build.mjs --estatico   -> dist/ consumindo snapshot JSON (./data/...), para o GitHub Pages
//   node build.mjs --watch      -> recompila ao salvar
import { build, context } from "esbuild";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const estatico = process.argv.includes("--estatico");
const watch = process.argv.includes("--watch");

rmSync("dist", { recursive: true, force: true });
mkdirSync("dist/assets", { recursive: true });

const opcoes = {
  entryPoints: { app: "src/main.tsx" },
  bundle: true,
  minify: !watch,
  sourcemap: watch ? "inline" : false,
  target: ["es2020"],
  outdir: "dist/assets",
  loader: { ".css": "css" },
  define: {
    __ESTATICO__: JSON.stringify(estatico),
    "process.env.NODE_ENV": JSON.stringify(watch ? "development" : "production"),
  },
  logLevel: "info",
};

const html = readFileSync("index.html", "utf8");
writeFileSync("dist/index.html", html);
if (estatico && existsSync("public/data")) cpSync("public/data", "dist/data", { recursive: true });

if (watch) {
  const ctx = await context(opcoes);
  await ctx.watch();
} else {
  await build(opcoes);
}
