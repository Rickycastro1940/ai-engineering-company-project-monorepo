import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { handleContact } from "./handlers.mjs";

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

function startSmtpSink() {
  const received = [];
  const server = net.createServer((socket) => {
    socket.write("220 sink ready\r\n");
    let buffer = "";
    let dataMode = false;
    let message = "";
    let authStep = 0;
    socket.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      if (dataMode) {
        message += buffer;
        buffer = "";
        if (message.includes("\r\n.\r\n")) {
          received.push(message);
          dataMode = false;
          message = "";
          socket.write("250 queued\r\n");
        }
        return;
      }
      let newline = buffer.indexOf("\r\n");
      while (newline !== -1) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 2);
        const command = line.toUpperCase();
        if (command.startsWith("EHLO")) socket.write("250-sink\r\n250 AUTH LOGIN\r\n");
        else if (command === "AUTH LOGIN") {
          authStep = 1;
          socket.write("334 VXNlcm5hbWU6\r\n");
        } else if (authStep === 1) {
          authStep = 2;
          socket.write("334 UGFzc3dvcmQ6\r\n");
        } else if (authStep === 2) {
          authStep = 0;
          socket.write("235 authenticated\r\n");
        } else if (command.startsWith("MAIL FROM") || command.startsWith("RCPT TO")) socket.write("250 ok\r\n");
        else if (command === "DATA") {
          dataMode = true;
          socket.write("354 go ahead\r\n");
        } else if (command === "QUIT") socket.write("221 bye\r\n");
        else socket.write("500 unknown\r\n");
        newline = buffer.indexOf("\r\n");
      }
    });
  });
  return { server, received, port: listen(server) };
}

const lead = {
  name: "Ada Lovelace",
  email: "ada@example.com",
  message: "Invoices are retyped into accounting every Friday.",
  company: "Analytical Engines",
  phone: "+1 954 555 0100",
  stack: "QuickBooks",
};

test("rejects an incomplete evaluation", async () => {
  const result = await handleContact({ name: "", email: "not-an-email", message: "" }, {});
  assert.equal(result.status, 422);
  assert.match(result.body.error, /valid email/);
});

test("honeypot does not open a mail connection", async () => {
  const result = await handleContact({ ...lead, website: "https://spam.test" }, {});
  assert.deepEqual(result, { status: 200, body: { ok: true } });
});

test("missing mailbox credentials reports that delivery is not configured", async () => {
  const result = await handleContact(lead, {});
  assert.equal(result.status, 501);
  assert.match(result.body.error, /not configured/);
});

test("a configured mailbox receives the evaluation", async () => {
  const sink = startSmtpSink();
  const port = await sink.port;
  const result = await handleContact(lead, {
    SMTP_HOST: "127.0.0.1",
    SMTP_PORT: String(port),
    SMTP_SECURE: "0",
    SMTP_USER: "info@advantageaisolutions.pro",
    SMTP_PASS: "mailbox-secret",
    CONTACT_TO: "info@advantageaisolutions.pro",
  });
  sink.server.close();
  assert.equal(result.status, 200);
  assert.equal(result.body.ok, true);
  assert.equal(sink.received.length, 1);
  const raw = sink.received[0];
  assert.match(raw, /From: info@advantageaisolutions\.pro/);
  assert.match(raw, /To: info@advantageaisolutions\.pro/);
  assert.match(raw, /Reply-To: ada@example.com/);
  assert.match(raw, /Subject: Systems evaluation from Ada Lovelace/);
  assert.match(raw, /Analytical Engines/);
  assert.match(raw, /retyped into accounting/);
  assert.doesNotMatch(raw, /mailbox-secret/);
});
