import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { handleChat, handleContact } from "./api/handlers.mjs";

const root = fileURLToPath(new URL(".", import.meta.url));
const port = Number(process.env.PORT || 4173);
const pages = {
  "/": "index.html",
  "/services": "services.html",
  "/contact": "contact.html",
};
const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".mjs": "text/javascript; charset=utf-8",
};

function send(res, status, body, type = "application/json; charset=utf-8") {
  res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-store" });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw) return {};
  return JSON.parse(raw);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || "/", "http://127.0.0.1");
  try {
    if (req.method === "POST" && (url.pathname === "/api/contact" || url.pathname === "/api/chat")) {
      const body = await readBody(req);
      const result = url.pathname === "/api/chat" ? await handleChat(body) : await handleContact(body);
      send(res, result.status, JSON.stringify(result.body));
      return;
    }
    if (req.method !== "GET" && req.method !== "HEAD") {
      send(res, 405, "");
      return;
    }
    const relative = pages[url.pathname] || url.pathname.replace(/^\/+/, "");
    const file = normalize(join(root, relative));
    if (!file.startsWith(root)) {
      send(res, 403, "Forbidden", "text/plain; charset=utf-8");
      return;
    }
    const data = await readFile(file);
    const type = types[extname(file)] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": type });
    res.end(req.method === "HEAD" ? undefined : data);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      send(res, 404, "Not found", "text/plain; charset=utf-8");
      return;
    }
    if (error instanceof SyntaxError) {
      send(res, 400, JSON.stringify({ error: "Invalid JSON." }));
      return;
    }
    send(res, 500, JSON.stringify({ error: "Something went wrong." }));
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Advantage AI site http://127.0.0.1:${port}`);
});
