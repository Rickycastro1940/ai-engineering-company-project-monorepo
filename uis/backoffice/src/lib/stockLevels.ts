/**
 * Kitchen on-hand stock bands for Brasaland Restaurant Operations (Felipe Guerrero).
 *
 * CONTEXT.md: ingredient orders still go out by WhatsApp, which produces
 * stockouts in some of the 14 locations and overstock in others.
 *
 * Thresholds (on-hand quantity, any unit):
 * - stockout: quantity === 0
 * - low: 1 <= quantity < 10
 * - healthy: 10 <= quantity < 100
 * - overstock: quantity >= 100
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

/** CONTEXT.md vocabulary: supplier delivery vs kitchen usage. */
export function supplyMovementLabel(orderType: string | undefined): string {
  const normalized = (orderType || "").trim().toUpperCase();
  if (normalized === "INBOUND") {
    return "Supplier delivery";
  }
  if (normalized === "OUTBOUND") {
    return "Kitchen usage";
  }
  return orderType?.trim() || "Unknown movement";
}

export function inboundOrderPath(ingredientId?: number): string {
  if (ingredientId == null || !Number.isFinite(ingredientId)) {
    return "/inventory/orders/inbound";
  }
  return `/inventory/orders/inbound?ingredient_id=${encodeURIComponent(String(ingredientId))}`;
}

export function outboundOrderPath(ingredientId?: number): string {
  if (ingredientId == null || !Number.isFinite(ingredientId)) {
    return "/inventory/orders/outbound";
  }
  return `/inventory/orders/outbound?ingredient_id=${encodeURIComponent(String(ingredientId))}`;
}

export function kitchenLocationLabel(locationId: number): string {
  const names = [
    "Medellín Centro",
    "Medellín El Poblado",
    "Bogotá Chapinero",
    "Bogotá Norte",
    "Cali Norte",
    "Barranquilla",
    "Cartagena",
    "Pereira",
    "Miami Brickell",
    "Miami Downtown",
    "Orlando",
    "Tampa",
    "Fort Lauderdale",
    "Jacksonville",
  ];
  if (locationId >= 1 && locationId <= names.length) {
    return names[locationId - 1];
  }
  return `Location ${locationId}`;
}
