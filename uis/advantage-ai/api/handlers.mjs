const CHAT_URL = "https://advantage-ai-solutions-api.vercel.app/chat";
const CONTACT_URL = process.env.CONTACT_UPSTREAM || "https://advantageaisolutions.pro/api/contact";

export async function handleChat(body) {
  const response = await fetch(CHAT_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: body?.message ?? "" }),
  });
  const payload = await response.json().catch(() => ({ error: "Invalid service response" }));
  return { status: response.status, body: payload };
}

export async function handleContact(body) {
  if (body && typeof body.website === "string" && body.website.trim()) {
    return { status: 200, body: { ok: true } };
  }
  const response = await fetch(CONTACT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-advantage-forward": "1",
    },
    body: JSON.stringify(body ?? {}),
  });
  if (response.status === 508 || response.headers.get("x-advantage-loop") === "1") {
    return {
      status: 501,
      body: { error: "Contact delivery is not configured on this deployment." },
    };
  }
  const payload = await response.json().catch(() => ({}));
  return { status: response.status, body: payload };
}
