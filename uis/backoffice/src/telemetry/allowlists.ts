/**
 * Property allowlists from docs/telemetry/event-schemas.json / telemetry-plan.md.
 * Only these keys may appear in `properties` for a given event_type.
 */

export const PROPERTY_ALLOWLISTS: Record<string, readonly string[]> = {
  inbound_order_created: [
    "location_id",
    "country",
    "product_id",
    "product_category",
    "quantity",
    "unit",
    "currency",
    "supplier_id",
  ],
  outbound_order_created: [
    "location_id",
    "country",
    "product_id",
    "product_category",
    "quantity",
    "unit",
    "currency",
  ],
  stock_waste_registered: [
    "location_id",
    "country",
    "product_id",
    "product_category",
    "quantity",
    "unit",
    "currency",
    "reason",
  ],
  stock_threshold_triggered: [
    "location_id",
    "country",
    "product_id",
    "product_category",
    "current_stock",
    "threshold",
    "unit",
    "currency",
  ],
  direct_stock_edit_rejected: ["location_id", "product_id", "reason"],
  ingredient_price_variance_detected: [
    "location_id",
    "country",
    "product_id",
    "supplier_id",
    "unit_cost",
    "historical_unit_cost",
    "variance_pct",
    "currency",
  ],
  order_validation_failed: ["product_id", "reason", "location_id"],
  login_failed: ["reason"],
  session_expired: ["route"],
  api_latency_recorded: ["endpoint", "method", "duration_ms", "status_code"],
  page_load_timed: ["route", "duration_ms"],
  frontend_error_caught: ["message", "route"],
  section_viewed: ["section", "route"],
  flow_abandoned: ["flow", "step", "route"],
  web_vital_reported: ["name", "value", "route"],
};

export function filterProperties(
  eventType: string,
  properties: Record<string, unknown>,
): Record<string, unknown> {
  const allowlist = PROPERTY_ALLOWLISTS[eventType];
  if (!allowlist) {
    console.warn(`No property allowlist for event_type=${eventType}`);
    return {};
  }
  const allowed = new Set(allowlist);
  const filtered: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(properties)) {
    if (allowed.has(key)) {
      filtered[key] = value;
    } else {
      console.warn(
        `Dropped property "${key}" for event_type=${eventType} (not in allowlist)`,
      );
    }
  }
  return filtered;
}
