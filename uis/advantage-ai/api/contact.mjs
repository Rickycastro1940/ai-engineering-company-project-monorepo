import { handleContact } from "./handlers.mjs";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).end();
    return;
  }
  if (req.headers["x-advantage-forward"] === "1") {
    res.setHeader("x-advantage-loop", "1");
    res.status(508).json({ error: "Contact delivery is not configured on this deployment." });
    return;
  }
  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : (req.body ?? {});
  const result = await handleContact(body);
  res.status(result.status).json(result.body);
}
