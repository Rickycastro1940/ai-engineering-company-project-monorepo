/**
 * Backoffice instrumentation wired to docs/telemetry/event-schemas.json.
 * All tracking goes through track() — never direct fetch/axios for telemetry.
 */

import { flush, setTelemetryUser, track as rawTrack } from "../services/telemetry";
import { filterProperties } from "./allowlists";

export const MAIN_SECTIONS = [
  { id: "dashboard", route: "/dashboard", label: "Dashboard" },
  { id: "inventory", route: "/inventory", label: "Inventory" },
  { id: "orders", route: "/orders", label: "Orders" },
  { id: "suppliers", route: "/suppliers", label: "Suppliers" },
  { id: "auth", route: "/auth", label: "Auth" },
] as const;

export type SectionId = (typeof MAIN_SECTIONS)[number]["id"];

let baselineBound = false;

/** Public track wrapper — enforces Phase 1 property allowlists. */
export function track(
  eventType: string,
  properties: Record<string, unknown> = {},
): void {
  rawTrack(eventType, filterProperties(eventType, properties));
}

export function initTelemetry(userId = "ops_demo"): void {
  setTelemetryUser(userId);
  bindTechnicalBaseline();
}

function recordPageLoad(): void {
  const nav = performance.getEntriesByType("navigation")[0] as
    | PerformanceNavigationTiming
    | undefined;
  const duration = nav
    ? Math.round(nav.loadEventEnd || performance.now())
    : Math.round(performance.now());
  if (duration > 0) {
    track("page_load_timed", {
      route: window.location.pathname,
      duration_ms: duration,
    });
  }
}

function bindTechnicalBaseline(): void {
  if (typeof window === "undefined" || baselineBound) return;
  baselineBound = true;

  window.addEventListener("error", (event) => {
    track("frontend_error_caught", {
      message: String(event.message || "error"),
      route: window.location.pathname,
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    track("frontend_error_caught", {
      message: String(event.reason ?? "unhandledrejection"),
      route: window.location.pathname,
    });
  });

  // Module may load after window "load"; still emit the performance baseline.
  if (document.readyState === "complete") {
    recordPageLoad();
  } else {
    window.addEventListener("load", recordPageLoad, { once: true });
  }
}

/** Navigation / page-view tracking for main backoffice sections. */
export function trackSectionView(sectionId: SectionId): void {
  const section = MAIN_SECTIONS.find((item) => item.id === sectionId);
  if (!section) return;
  track("section_viewed", {
    section: section.id,
    route: section.route,
  });
}

/** Record API latency for a relevant backoffice call. */
export function trackApiLatency(props: {
  endpoint: string;
  method: string;
  duration_ms: number;
  status_code: number;
}): void {
  track("api_latency_recorded", props);
}

/** Mandatory CONTEXT metrics — called from inventory/order handlers. */
export const inventoryTelemetry = {
  inboundCreated(props: {
    location_id: string;
    country: "CO" | "US";
    product_id: string;
    product_category: string;
    quantity: number;
    unit: string;
    currency: "COP" | "USD";
    supplier_id: string;
  }) {
    track("inbound_order_created", props);
  },
  outboundCreated(props: {
    location_id: string;
    country: "CO" | "US";
    product_id: string;
    product_category: string;
    quantity: number;
    unit: string;
    currency: "COP" | "USD";
  }) {
    track("outbound_order_created", props);
  },
  wasteRegistered(props: {
    location_id: string;
    country: "CO" | "US";
    product_id: string;
    product_category: string;
    quantity: number;
    unit: string;
    currency: "COP" | "USD";
    reason: "expired" | "kitchen_error" | "theft_suspected";
  }) {
    track("stock_waste_registered", props);
  },
  thresholdTriggered(props: {
    location_id: string;
    country: "CO" | "US";
    product_id: string;
    product_category: string;
    current_stock: number;
    threshold: number;
    unit: string;
    currency: "COP" | "USD";
  }) {
    track("stock_threshold_triggered", props);
  },
  directEditRejected(props: {
    location_id: string;
    product_id: string;
    reason: string;
  }) {
    track("direct_stock_edit_rejected", props);
  },
  priceVariance(props: {
    location_id: string;
    country: "CO" | "US";
    product_id: string;
    supplier_id: string;
    unit_cost: number;
    historical_unit_cost: number;
    variance_pct: number;
    currency: "COP" | "USD";
  }) {
    track("ingredient_price_variance_detected", props);
  },
  validationFailed(props: {
    location_id: string;
    product_id: string;
    reason: string;
  }) {
    track("order_validation_failed", props);
  },
};

export const authTelemetry = {
  loginFailed(reason: "invalid_credentials" | "session_expired" | "network_error") {
    track("login_failed", { reason });
  },
  sessionExpired(route: string) {
    track("session_expired", { route });
  },
};

export { flush };
