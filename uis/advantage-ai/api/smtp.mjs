import net from "node:net";
import tls from "node:tls";

const DEFAULT_HOST = "smtp.hostinger.com";
const DEFAULT_PORT = 465;

function headerValue(value) {
  return String(value ?? "").replace(/[\r\n]+/g, " ").trim();
}

function createReader(socket) {
  let pending = "";
  const waiters = [];
  socket.on("data", (chunk) => {
    pending += chunk.toString("utf8");
    drain();
  });
  socket.on("error", (error) => {
    while (waiters.length) waiters.shift().reject(error);
  });

  function takeResponse() {
    const lines = pending.split(/\r?\n/);
    for (let index = 0; index < lines.length - 1; index += 1) {
      if (!/^\d{3} /.test(lines[index])) continue;
      const used = lines.slice(0, index + 1);
      const rest = lines.slice(index + 1);
      pending = rest.length > 1 || rest[0] ? rest.join("\r\n") : "";
      const last = used.at(-1);
      return { code: Number(last.slice(0, 3)), text: used.join("\n") };
    }
    return null;
  }

  function drain() {
    while (waiters.length) {
      const next = takeResponse();
      if (!next) return;
      waiters.shift().resolve(next);
    }
  }

  return function readResponse() {
    const ready = takeResponse();
    if (ready) return Promise.resolve(ready);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const index = waiters.findIndex((waiter) => waiter.resolve === resolve);
        if (index !== -1) waiters.splice(index, 1);
        reject(new Error("SMTP server timed out"));
      }, 15000);
      waiters.push({
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
    });
  };
}

function sendLine(socket, line) {
  socket.write(`${line}\r\n`);
}

export function mailSettings(env = process.env) {
  const user = headerValue(env.SMTP_USER);
  const pass = env.SMTP_PASS ?? "";
  const to = headerValue(env.CONTACT_TO || "info@advantageaisolutions.pro");
  const from = headerValue(env.CONTACT_FROM || user);
  const host = headerValue(env.SMTP_HOST || DEFAULT_HOST);
  const port = Number(env.SMTP_PORT || DEFAULT_PORT);
  const secure = env.SMTP_SECURE ? env.SMTP_SECURE !== "0" : port === 465;
  return { user, pass, to, from, host, port, secure, configured: Boolean(user && pass && from && to) };
}

export async function sendEvaluation(fields, env = process.env) {
  const settings = mailSettings(env);
  if (!settings.configured) {
    const error = new Error("Contact delivery is not configured on this deployment.");
    error.status = 501;
    throw error;
  }
  const subject = headerValue(`Systems evaluation from ${fields.name}`).slice(0, 180);
  const lines = [
    `Name: ${fields.name}`,
    `Email: ${fields.email}`,
    fields.company ? `Company: ${fields.company}` : "",
    fields.phone ? `Phone: ${fields.phone}` : "",
    fields.stack ? `Current software: ${fields.stack}` : "",
    "",
    fields.message,
  ].filter((line) => line !== "");
  const text = lines.join("\n").replace(/^\./gm, "..");
  const message = [
    `From: ${settings.from}`,
    `To: ${settings.to}`,
    `Reply-To: ${headerValue(fields.email)}`,
    `Subject: ${subject}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "",
    text,
    ".",
  ].join("\r\n");

  const socket = settings.secure
    ? tls.connect({ host: settings.host, port: settings.port, servername: settings.host })
    : net.connect({ host: settings.host, port: settings.port });
  const readResponse = createReader(socket);

  try {
    await new Promise((resolve, reject) => {
      socket.once("secureConnect", resolve);
      socket.once("connect", () => {
        if (!settings.secure) resolve();
      });
      socket.once("error", reject);
    });
    const greeting = await readResponse();
    if (greeting.code !== 220) throw new Error("SMTP greeting failed");
    sendLine(socket, "EHLO advantageaisolutions.pro");
    const hello = await readResponse();
    if (hello.code !== 250) throw new Error("SMTP EHLO failed");
    sendLine(socket, "AUTH LOGIN");
    const userPrompt = await readResponse();
    if (userPrompt.code !== 334) throw new Error("SMTP auth was refused");
    sendLine(socket, Buffer.from(settings.user).toString("base64"));
    const passPrompt = await readResponse();
    if (passPrompt.code !== 334) throw new Error("SMTP auth was refused");
    sendLine(socket, Buffer.from(settings.pass).toString("base64"));
    const authed = await readResponse();
    if (authed.code !== 235) throw new Error("SMTP login failed");
    sendLine(socket, `MAIL FROM:<${settings.from}>`);
    if ((await readResponse()).code !== 250) throw new Error("MAIL FROM failed");
    sendLine(socket, `RCPT TO:<${settings.to}>`);
    if ((await readResponse()).code !== 250) throw new Error("RCPT TO failed");
    sendLine(socket, "DATA");
    if ((await readResponse()).code !== 354) throw new Error("DATA was refused");
    socket.write(`${message}\r\n`);
    if ((await readResponse()).code !== 250) throw new Error("Message was refused");
    sendLine(socket, "QUIT");
    await readResponse().catch(() => {});
  } finally {
    socket.end();
  }
}
