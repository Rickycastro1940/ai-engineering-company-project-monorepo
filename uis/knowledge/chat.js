import { reconnectDelayMs } from "./reconnect.js";

const loginForm = document.querySelector("#login");
const chat = document.querySelector("#chat");
const statusLine = document.querySelector("#status");
const log = document.querySelector("#log");
const sessionLine = document.querySelector("#session");
const askForm = document.querySelector("#ask");
const contentBox = document.querySelector("#content");
const sendButton = document.querySelector("#send");
const stopButton = document.querySelector("#stop");
const reconnectButton = document.querySelector("#reconnect");

let token = "";
let sessionId = "";
let socket = null;
let liveBubble = null;
let sawCheckpoint = false;
let attempt = 0;
let reconnectTimer = null;
let generation = 0;

function setStatus(text) {
  statusLine.textContent = text;
}

function addBubble(role, text) {
  const node = document.createElement("p");
  node.className = `bubble ${role}`;
  node.textContent = text;
  log.appendChild(node);
  return node;
}

function renderHistory(messages, draft) {
  log.replaceChildren();
  liveBubble = null;
  for (const message of messages || []) {
    const bubble = addBubble(message.role === "user" ? "user" : "assistant", message.content || "");
    if (message.role === "assistant" && message.status === "interrupted") {
      bubble.dataset.state = "interrupted";
    }
  }
  if (draft) {
    liveBubble = addBubble("assistant", draft);
  }
}

async function createSession() {
  const response = await fetch("/knowledge/sessions", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error("The chat session could not be opened.");
  }
  const body = await response.json();
  sessionId = body.session_id;
  sessionLine.textContent = sessionId;
}

function connect() {
  const mine = ++generation;
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  sawCheckpoint = false;
  if (socket) {
    socket.close();
  }
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${location.host}/knowledge/ws?token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(sessionId)}`;
  socket = new WebSocket(url);
  setStatus("Connecting");
  socket.addEventListener("open", () => {
    if (mine !== generation) {
      return;
    }
    attempt = 0;
    setStatus("Live");
  });
  socket.addEventListener("close", () => {
    if (mine !== generation || !sessionId) {
      return;
    }
    const delay = reconnectDelayMs(attempt);
    attempt += 1;
    setStatus(`Reconnecting in ${delay / 1000}s`);
    reconnectTimer = window.setTimeout(connect, delay);
  });
  socket.addEventListener("message", (event) => {
    if (mine !== generation) {
      return;
    }
    const frame = JSON.parse(event.data);
    if (frame.event === "support_session") {
      sessionLine.textContent = frame.session_id;
      if (!sawCheckpoint) {
        renderHistory(frame.messages, frame.draft);
        sawCheckpoint = true;
      }
      if (frame.status === "streaming") {
        setStatus("Streaming");
      } else if (frame.status === "interrupted") {
        setStatus("Interrupted");
      } else {
        setStatus("Live");
      }
    } else if (frame.event === "token_chunk") {
      if (!liveBubble) {
        liveBubble = addBubble("assistant", "");
      }
      liveBubble.textContent += frame.delta || "";
      setStatus("Streaming");
    } else if (frame.event === "support_assistant_message") {
      if (!liveBubble) {
        liveBubble = addBubble("assistant", frame.content || "");
      }
      if (frame.status === "interrupted") {
        liveBubble.dataset.state = "interrupted";
      }
      liveBubble = null;
      setStatus(frame.status === "interrupted" ? "Interrupted" : "Live");
    } else if (frame.event === "support_error") {
      const note = document.createElement("p");
      note.className = "error";
      note.textContent = frame.detail || "The assistant could not answer.";
      log.appendChild(note);
    }
  });
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Signing in");
  const response = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: document.querySelector("#email").value.trim(),
      password: document.querySelector("#password").value,
    }),
  });
  if (!response.ok) {
    setStatus("Sign-in failed. Check the email and password.");
    return;
  }
  const body = await response.json();
  token = body.access_token;
  await createSession();
  loginForm.hidden = true;
  chat.hidden = false;
  connect();
});

askForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = contentBox.value.trim();
  if (!content || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  addBubble("user", content);
  liveBubble = null;
  socket.send(JSON.stringify({ event: "support_user_message", content }));
  contentBox.value = "";
});

stopButton.addEventListener("click", () => {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(JSON.stringify({ event: "support_interrupt" }));
});

reconnectButton.addEventListener("click", () => {
  attempt = 0;
  connect();
});
