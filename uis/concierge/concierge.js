/** Guest concierge. Tokens arrive on the WebSocket; SSE is the one-way replay path. */
(function () {
  const status = document.getElementById("status");
  const log = document.getElementById("log");
  const open = document.getElementById("open");
  const form = document.getElementById("composer");
  const content = document.getElementById("content");
  const audio = document.getElementById("audio");
  const send = document.getElementById("send");
  const stop = document.getElementById("stop");
  const storageKey = "brasaland-guest-concierge-session";

  let socket = null;
  let sessionId = sessionStorage.getItem(storageKey) || "";
  let live = null;

  function setStatus(text, isError) {
    status.textContent = text;
    status.className = isError ? "status error" : "status";
  }

  function bubble(role) {
    const node = document.createElement("div");
    node.className = "bubble " + role;
    log.appendChild(node);
    return node;
  }

  function restore(messages) {
    log.replaceChildren();
    (messages || []).forEach(function (row) {
      const node = bubble(row.role === "user" ? "user" : "assistant");
      node.textContent = row.content || "";
    });
  }

  function connect(id) {
    if (socket) {
      socket.close();
    }
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(
      protocol + "://" + location.host + "/concierge/ws?session_id=" + encodeURIComponent(id)
    );
    socket.addEventListener("open", function () {
      setStatus("Connected. Ask about the menu, allergens, or an order.");
    });
    socket.addEventListener("message", function (event) {
      const frame = JSON.parse(event.data);
      if (frame.event === "concierge_session" || frame.event === "concierge_snapshot") {
        if (!live) {
          restore(frame.messages);
        }
        return;
      }
      if (frame.event === "token_chunk") {
        if (!live) {
          live = bubble("assistant");
        }
        live.textContent += frame.delta || "";
        return;
      }
      if (frame.event === "generation_completed" || frame.event === "generation_interrupted") {
        if (live) {
          live.textContent = frame.content || live.textContent;
        }
        live = null;
        send.disabled = false;
        return;
      }
      if (frame.event === "concierge_order") {
        setStatus("Order placed at " + (frame.order.location_name || "the kitchen") + ".");
        return;
      }
      if (frame.event === "concierge_error") {
        setStatus(frame.detail || "The concierge could not read that.", true);
        send.disabled = false;
      }
    });
    socket.addEventListener("close", function () {
      setStatus("Disconnected. Start the conversation again.");
      send.disabled = false;
    });
  }

  async function ensureSession() {
    if (sessionId) {
      const existing = await fetch("/concierge/sessions/" + encodeURIComponent(sessionId));
      if (existing.ok) {
        return sessionId;
      }
    }
    const created = await fetch("/concierge/sessions", { method: "POST" });
    if (!created.ok) {
      throw new Error("Could not open a concierge session.");
    }
    const body = await created.json();
    sessionId = body.session_id;
    sessionStorage.setItem(storageKey, sessionId);
    return sessionId;
  }

  open.addEventListener("click", async function () {
    try {
      const id = await ensureSession();
      connect(id);
    } catch (error) {
      setStatus(error.message || "Could not start.", true);
    }
  });

  async function transcriptFromAudio(file) {
    const data = new FormData();
    data.set("audio", file);
    const typed = content.value.trim();
    if (typed) {
      data.set("text", typed);
    }
    const response = await fetch("/concierge/transcribe", { method: "POST", body: data });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.detail || "Transcription failed.");
    }
    if (!body.transcript) {
      throw new Error(body.detail || "Type the order. No audio key is set.");
    }
    if (body.mode === "text_fallback") {
      setStatus("Voice model is off. Sending the typed order.");
    }
    return body.transcript;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setStatus("Start the conversation first.", true);
      return;
    }
    send.disabled = true;
    try {
      let text = content.value.trim();
      const file = audio.files && audio.files[0];
      if (file) {
        text = await transcriptFromAudio(file);
        audio.value = "";
      }
      if (!text) {
        setStatus("Type an order or attach a voice clip.", true);
        send.disabled = false;
        return;
      }
      bubble("user").textContent = text;
      content.value = "";
      socket.send(JSON.stringify({ event: "concierge_user_message", content: text }));
    } catch (error) {
      setStatus(error.message || "Could not send that.", true);
      send.disabled = false;
    }
  });

  stop.addEventListener("click", function () {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ event: "interrupt" }));
    }
  });
})();
