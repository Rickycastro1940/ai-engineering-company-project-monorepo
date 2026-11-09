const menu = document.querySelector(".menu-btn");
const nav = document.getElementById("site-nav");
if (menu && nav) {
  menu.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    menu.setAttribute("aria-expanded", open ? "true" : "false");
  });
}

const askForm = document.getElementById("ask-form");
const askInput = document.getElementById("ask-input");
const askResult = document.getElementById("ask-result");
let askController = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char]));
}

function renderAnswer(data) {
  const sources = (data.sources || [])
    .map((source) => `<li><a href="${escapeHtml(source.url)}">${escapeHtml(source.title)}</a></li>`)
    .join("");
  askResult.innerHTML = `<p>${escapeHtml(data.answer)}</p>${sources ? `<ul class="sources">${sources}</ul>` : ""}`;
}

async function ask(question) {
  const text = question.trim();
  if (text.length < 3 || text.length > 1000) {
    askResult.innerHTML = `<p class="error">Enter a question between 3 and 1,000 characters.</p>`;
    return;
  }
  if (askController) askController.abort();
  askController = new AbortController();
  const timer = window.setTimeout(() => askController.abort(), 20000);
  askResult.innerHTML = `<p class="note">Looking through Advantage’s public service notes…</p>`;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
      signal: askController.signal,
    });
    if (!response.ok) throw new Error("Service request failed");
    const data = await response.json();
    if (
      !data ||
      data.business !== "Advantage AI Solutions" ||
      data.mode !== "curated_retrieval" ||
      typeof data.answer !== "string" ||
      typeof data.supported !== "boolean" ||
      !Array.isArray(data.sources)
    ) {
      throw new Error("Unexpected service response");
    }
    const sources = data.sources.flatMap((source) => {
      try {
        const url = new URL(source.url);
        if (url.origin !== "https://advantageaisolutions.pro") return [];
        if (typeof source.title !== "string") return [];
        return [{ title: source.title, url: url.href }];
      } catch {
        return [];
      }
    });
    renderAnswer({ answer: data.answer, sources });
  } catch {
    askResult.innerHTML = `<p class="error">We couldn’t reach the service assistant. Please try again, or <a href="/contact">request a Systems Evaluation</a>.</p>`;
  } finally {
    window.clearTimeout(timer);
    askController = null;
  }
}

if (askForm && askInput && askResult) {
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      askInput.value = button.getAttribute("data-question");
      ask(askInput.value);
    });
  });
  askForm.addEventListener("submit", (event) => {
    event.preventDefault();
    ask(askInput.value);
  });
}

const contactForm = document.getElementById("contact-form");
const contactStatus = document.getElementById("contact-status");
if (contactForm && contactStatus) {
  contactForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = contactForm.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Sending…";
    contactStatus.innerHTML = "";
    const payload = Object.fromEntries(new FormData(contactForm));
    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Something went wrong.");
      contactForm.hidden = true;
      contactStatus.innerHTML = `<div class="status" role="status"><h3>Your evaluation request is received</h3><p>Your request was sent to info@advantageaisolutions.pro. An engineer will review it and reply within one business day.</p></div>`;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Something went wrong.";
      contactStatus.innerHTML = `<div class="status error-box" role="alert"><p class="error">${escapeHtml(message)} You can also email <a href="mailto:info@advantageaisolutions.pro">info@advantageaisolutions.pro</a>.</p></div>`;
      button.disabled = false;
      button.textContent = "Request a Systems Evaluation";
    }
  });
}
