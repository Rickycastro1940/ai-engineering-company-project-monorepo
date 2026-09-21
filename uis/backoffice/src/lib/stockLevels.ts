/**
 * Kitchen on-hand stock bands for Brasaland Restaurant Operations (Felipe Guerrero).
 *
 * CONTEXT.md: ingredient orders still go out by WhatsApp, which produces
 * stockouts in some of the 14 locations and overstock in others. The central
 * inventory API uses a default low-stock alert of 10 (`GET /inventory/alerts`).
 *
 * Thresholds (on-hand quantity, any unit):
 * - stockout: quantity === 0 — kitchen cannot plate until an inbound order arrives
 * - low: 1 <= quantity < 10 — below the API alert threshold; treat as emergency inbound
 * - healthy: 10 <= quantity < 100 — enough on hand to keep the line moving
 * - overstock: quantity >= 100 — surplus that CONTEXT.md flags as the other
 *   failure mode of blind ordering (typical for packaging such as napkins)
 */
export const STOCKOUT_MAX = 0;
export const LOW_STOCK_MAX_EXCLUSIVE = 10;
export const OVERSTOCK_MIN = 100;

export type StockLevel = "stockout" | "low" | "healthy" | "overstock";

export function currentStockOf(product: {
  current_stock?: number;
  quantity?: number;
} | null): number | null {
  if (!product) {
    return null;
  }
  const stock = product.current_stock ?? product.quantity;
  return Number.isFinite(Number(stock)) ? Number(stock) : null;
}

export function stockLevelForQuantity(quantity: number): StockLevel {
  if (!Number.isFinite(quantity) || quantity <= STOCKOUT_MAX) {
    return "stockout";
  }
  if (quantity < LOW_STOCK_MAX_EXCLUSIVE) {
    return "low";
  }
  if (quantity >= OVERSTOCK_MIN) {
    return "overstock";
  }
  return "healthy";
}

export function stockLevelLabel(level: StockLevel): string {
  if (level === "stockout") {
    return "Stockout";
  }
  if (level === "low") {
    return "Low stock";
  }
  if (level === "overstock") {
    return "Overstock";
  }
  return "Healthy stock";
}

/** CONTEXT.md: locations place supply orders with suppliers; kitchens consume stock. */
export function supplyMovementLabel(orderType: string | undefined): string {
  if (orderType === "inbound") {
    return "Supplier delivery";
  }
  if (orderType === "outbound") {
    return "Kitchen usage";
  }
  const trimmed = orderType?.trim();
  return trimmed || "Unknown movement";
}

export function inboundOrderPath(productId?: number): string {
  if (productId == null || !Number.isFinite(productId)) {
    return "/inventory/orders/inbound";
  }
  return `/inventory/orders/inbound?product_id=${encodeURIComponent(String(productId))}`;
}

export function outboundOrderPath(productId?: number): string {
  if (productId == null || !Number.isFinite(productId)) {
    return "/inventory/orders/outbound";
  }
  return `/inventory/orders/outbound?product_id=${encodeURIComponent(String(productId))}`;
}
