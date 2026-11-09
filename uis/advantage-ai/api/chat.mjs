import { handleChat } from "./handlers.mjs";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).end();
    return;
  }
  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body ?? {});
  const result = await handleChat(body);
  res.status(result.status).json(result.body);
}
