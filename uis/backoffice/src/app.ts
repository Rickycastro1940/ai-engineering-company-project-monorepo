import {
  MAIN_SECTIONS,
  SectionId,
  authTelemetry,
  flush,
  inventoryTelemetry,
  trackApiLatency,
  trackSectionView,
} from "./telemetry/instrumentation";

const PRODUCT = {
  location_id: "med-001",
  country: "CO" as const,
  product_id: "beef_loin",
  product_category: "protein",
  unit: "kg",
  currency: "COP" as const,
  supplier_id: "sup-co-01",
};

let activeSection: SectionId = "inventory";
let sectionAbort: AbortController | null = null;

export function mountBackoffice(root: HTMLElement): void {
  root.innerHTML = `
    <header class="top">
      <strong>Brasaland Backoffice</strong>
      <span class="muted">Telemetry capture demo</span>
      <button type="button" id="flush-now">Flush telemetry now</button>
    </header>
    <nav class="nav" id="main-nav"></nav>
    <main id="section-root" class="section"></main>
    <p id="status" class="status" role="status"></p>
  `;

  const nav = root.querySelector<HTMLElement>("#main-nav")!;
  nav.innerHTML = MAIN_SECTIONS.map(
    (section) =>
      `<button type="button" data-section="${section.id}">${section.label}</button>`,
  ).join("");

  nav.addEventListener("click", (event) => {
    const target = (event.target as HTMLElement).closest<HTMLButtonElement>(
      "button[data-section]",
    );
    if (!target?.dataset.section) return;
    showSection(target.dataset.section as SectionId);
  });

  root.querySelector("#flush-now")?.addEventListener("click", () => {
    void flush().then(() => setStatus("Telemetry queue flushed."));
  });

  showSection("inventory");
}

function showSection(sectionId: SectionId): void {
  activeSection = sectionId;
  trackSectionView(sectionId);

  sectionAbort?.abort();
  sectionAbort = new AbortController();
  const { signal } = sectionAbort;

  document
    .querySelectorAll<HTMLButtonElement>("#main-nav button")
    .forEach((button) => {
      button.classList.toggle("active", button.dataset.section === sectionId);
    });

  const sectionRoot = document.querySelector<HTMLElement>("#section-root")!;
  if (sectionId === "inventory" || sectionId === "orders") {
    sectionRoot.innerHTML = inventoryPanel();
    bindInventoryHandlers(sectionRoot, signal);
    return;
  }
  if (sectionId === "auth") {
    sectionRoot.innerHTML = authPanel();
    bindAuthHandlers(sectionRoot, signal);
    return;
  }
  if (sectionId === "suppliers") {
    sectionRoot.innerHTML = `
      <h1>Suppliers</h1>
      <p>Price variance checks run when inbound unit cost drifts.</p>
      <button type="button" data-action="price-variance">Simulate price variance</button>
    `;
    sectionRoot.addEventListener(
      "click",
      (event) => {
        const action = (event.target as HTMLElement)
          .closest<HTMLButtonElement>("button[data-action]")
          ?.dataset.action;
        if (action !== "price-variance") return;
        inventoryTelemetry.priceVariance({
          location_id: PRODUCT.location_id,
          country: PRODUCT.country,
          product_id: PRODUCT.product_id,
          supplier_id: PRODUCT.supplier_id,
          unit_cost: 44000,
          historical_unit_cost: 38000,
          variance_pct: 15.8,
          currency: PRODUCT.currency,
        });
        setStatus("Tracked ingredient_price_variance_detected");
      },
      { signal },
    );
    return;
  }

  sectionRoot.innerHTML = `
    <h1>Dashboard</h1>
    <p>Operations overview for Colombia + Florida locations.</p>
  `;
}

function inventoryPanel(): string {
  return `
    <h1>${activeSection === "orders" ? "Orders" : "Inventory"}</h1>
    <p>Actions below fire CONTEXT mandatory metrics through <code>track()</code>.</p>
    <div class="actions">
      <button type="button" data-action="inbound">Register inbound order</button>
      <button type="button" data-action="outbound">Register outbound order</button>
      <button type="button" data-action="waste">Register waste</button>
      <button type="button" data-action="threshold">Trigger stock threshold</button>
      <button type="button" data-action="direct-edit">Attempt direct stock edit</button>
      <button type="button" data-action="price-variance">Detect price variance</button>
      <button type="button" data-action="validation-failed">Order validation failed</button>
      <button type="button" data-action="api-latency">Simulate API latency sample</button>
    </div>
  `;
}

function authPanel(): string {
  return `
    <h1>Auth</h1>
    <form id="login-form">
      <label>Operator id <input name="userId" value="ops_med_001" autocomplete="username" /></label>
      <label>Password <input name="password" type="password" value="wrong" autocomplete="current-password" /></label>
      <button type="submit">Sign in</button>
    </form>
    <button type="button" data-action="session-expired">Simulate session expired</button>
  `;
}

function bindInventoryHandlers(root: HTMLElement, signal: AbortSignal): void {
  root.addEventListener(
    "click",
    async (event) => {
      const action = (event.target as HTMLElement)
        .closest<HTMLButtonElement>("button[data-action]")
        ?.dataset.action;
      if (!action) return;

      if (action === "inbound") {
        inventoryTelemetry.inboundCreated({
          ...PRODUCT,
          quantity: 12,
        });
        setStatus("Tracked inbound_order_created");
        return;
      }
      if (action === "outbound") {
        inventoryTelemetry.outboundCreated({
          location_id: PRODUCT.location_id,
          country: PRODUCT.country,
          product_id: PRODUCT.product_id,
          product_category: PRODUCT.product_category,
          quantity: 3,
          unit: PRODUCT.unit,
          currency: PRODUCT.currency,
        });
        setStatus("Tracked outbound_order_created");
        return;
      }
      if (action === "waste") {
        inventoryTelemetry.wasteRegistered({
          ...PRODUCT,
          quantity: 1.5,
          reason: "expired",
        });
        setStatus("Tracked stock_waste_registered");
        return;
      }
      if (action === "threshold") {
        inventoryTelemetry.thresholdTriggered({
          location_id: PRODUCT.location_id,
          country: PRODUCT.country,
          product_id: PRODUCT.product_id,
          product_category: PRODUCT.product_category,
          current_stock: 2,
          threshold: 5,
          unit: PRODUCT.unit,
          currency: PRODUCT.currency,
        });
        setStatus("Tracked stock_threshold_triggered");
        return;
      }
      if (action === "direct-edit") {
        inventoryTelemetry.directEditRejected({
          location_id: PRODUCT.location_id,
          product_id: PRODUCT.product_id,
          reason: "stock_must_change_via_orders",
        });
        setStatus("Tracked direct_stock_edit_rejected");
        return;
      }
      if (action === "price-variance") {
        inventoryTelemetry.priceVariance({
          location_id: PRODUCT.location_id,
          country: PRODUCT.country,
          product_id: PRODUCT.product_id,
          supplier_id: PRODUCT.supplier_id,
          unit_cost: 44000,
          historical_unit_cost: 38000,
          variance_pct: 15.8,
          currency: PRODUCT.currency,
        });
        setStatus("Tracked ingredient_price_variance_detected");
        return;
      }
      if (action === "validation-failed") {
        inventoryTelemetry.validationFailed({
          location_id: PRODUCT.location_id,
          product_id: PRODUCT.product_id,
          reason: "quantity_must_be_positive",
        });
        setStatus("Tracked order_validation_failed");
        return;
      }
      if (action === "api-latency") {
        const started = performance.now();
        await new Promise((resolve) => setTimeout(resolve, 35));
        trackApiLatency({
          endpoint: "/api/v1/inventory/stock",
          method: "GET",
          duration_ms: Math.round(performance.now() - started),
          status_code: 200,
        });
        setStatus("Tracked api_latency_recorded");
      }
    },
    { signal },
  );
}

function bindAuthHandlers(root: HTMLElement, signal: AbortSignal): void {
  root.querySelector("#login-form")?.addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      // Never send password/email in telemetry properties.
      authTelemetry.loginFailed("invalid_credentials");
      setStatus("Tracked login_failed (reason only, no credentials)");
    },
    { signal },
  );
  root.addEventListener(
    "click",
    (event) => {
      const action = (event.target as HTMLElement)
        .closest<HTMLButtonElement>("button[data-action]")
        ?.dataset.action;
      if (action !== "session-expired") return;
      authTelemetry.sessionExpired("/auth");
      setStatus("Tracked session_expired");
    },
    { signal },
  );
}

function setStatus(message: string): void {
  const status = document.querySelector("#status");
  if (status) status.textContent = message;
}
