import { spawn } from "node:child_process";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { site } from "./site.config.mjs";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
const pages = ["index.html", "services.html", "contact.html", "404.html"];
const assets = ["styles.css", "app.js", "icon.svg", "sitemap.xml"];

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: root, stdio: "inherit" });
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(" ")} exited ${code}`));
    });
  });
}

await run(process.execPath, ["--test", join(root, "api/contact.test.mjs")]);

for (const page of pages) {
  const html = await readFile(join(root, page), "utf8");
  if (!html.includes(site.mailbox)) {
    throw new Error(`${page} is missing ${site.mailbox}`);
  }
  if (!html.includes('href="/styles.css"')) {
    throw new Error(`${page} is missing the stylesheet`);
  }
}

for (const asset of assets) {
  await readFile(join(root, asset));
}

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
const shipped = [...pages, ...assets, "vercel.json", "server.mjs", "site.config.mjs"];
for (const file of shipped) {
  await cp(join(root, file), join(dist, file));
}
await cp(join(root, "api"), join(dist, "api"), { recursive: true });
const built = [];
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) await walk(path);
    else built.push(path.slice(dist.length + 1));
  }
}
await walk(dist);
const stamp = {
  name: site.name,
  origin: site.origin,
  mailbox: site.mailbox,
  smtpHost: site.smtpHost,
  smtpPort: site.smtpPort,
  files: built.sort(),
};
await writeFile(join(dist, "build.json"), `${JSON.stringify(stamp, null, 2)}\n`);
console.log(`Built ${site.name} for ${site.mailbox}`);
console.log(`Output ${dist} (${stamp.files.length + 1} files)`);
