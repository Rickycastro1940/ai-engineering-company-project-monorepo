import { site } from "../site.config.mjs";
import { sendEvaluation } from "./smtp.mjs";

export const LIVE_CONTACT = `${site.origin}/api/contact`;

const CHAT_URL = "https://advantage-ai-solutions-api.vercel.app/chat";
const VALIDATION_ERROR = "Please add your name, a valid email and your workflow bottleneck.";
const SEND_ERROR = "We couldn't send your message right now.";

export async function handleChat(body) {
  const response = await fetch(CHAT_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: body?.message ?? "" }),
  });
  const payload = await response.json().catch(() => ({ error: "Invalid service response" }));
  return { status: response.status, body: payload };
}

function field(value) {
  return typeof value === "string" ? value.replace(/[\r\n]+/g, " ").trim() : "";
}

function validEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) && value.length <= 254;
}

export function contactFields(body) {
  return {
    website: field(body?.website),
    name: field(body?.name),
    email: field(body?.email),
    message: typeof body?.message === "string" ? body.message.replace(/\r\n/g, "\n").trim() : "",
    company: field(body?.company),
    phone: field(body?.phone),
    stack: field(body?.stack),
  };
}

export async function handleContact(body, env = process.env) {
  const fields = contactFields(body);
  if (fields.website) return { status: 200, body: { ok: true } };
  if (!fields.name || !validEmail(fields.email) || !fields.message) {
    return { status: 422, body: { error: VALIDATION_ERROR } };
  }

  const upstream = (env.CONTACT_UPSTREAM || LIVE_CONTACT).trim();
  if (!env.SMTP_PASS) {
    if (upstream === "off") {
      return { status: 501, body: { error: "Contact delivery is not configured on this deployment." } };
    }
    const response = await fetch(upstream, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-advantage-forward": "1" },
      body: JSON.stringify(body ?? {}),
    });
    if (response.status === 508 || response.headers.get("x-advantage-loop") === "1") {
      return { status: 501, body: { error: "Contact delivery is not configured on this deployment." } };
    }
    const payload = await response.json().catch(() => ({}));
    return { status: response.status, body: payload };
  }

  try {
    await sendEvaluation(fields, env);
    return { status: 200, body: { ok: true } };
  } catch (error) {
    if (error && error.status === 501) {
      return { status: 501, body: { error: error.message } };
    }
    return { status: 502, body: { error: SEND_ERROR } };
  }
}
