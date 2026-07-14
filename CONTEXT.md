# CONTEXT — Brasaland (Telemetry)

Source: course CONTEXT for telemetry projects. Full inventory/ops constraints for capture, storage, and reporting.

## Company

Brasaland is a grilled-food restaurant chain with 14 locations across Colombia and Florida. The inventory management system controls ingredients (meats, vegetables, sauces, beverages, packaging). Telemetry Plan, capture, storage, and technical report revolve around that system.

## Inventory entities

| Entity | Meaning |
| --- | --- |
| `Product` | Ingredient/supply (e.g. beef loin, house sauce) with unit and category |
| `InboundOrder` | Goods received from a supplier at a location |
| `OutboundOrder` | Consumption in prep, or recorded waste |
| `location` | One of 14 locations (`CO` / `US` + city) |
| `supplier` | ~20 suppliers, different per country |

## Mandatory telemetry metrics

| `event_type` | Fires when… |
| --- | --- |
| `inbound_order_created` | Location registers supplier arrival |
| `outbound_order_created` | Location registers prep consumption |
| `stock_waste_registered` | Waste (expired / kitchen_error / theft_suspected) |
| `stock_threshold_triggered` | Stock below configured minimum |
| `direct_stock_edit_rejected` | Direct stock edit blocked by system |
| `ingredient_price_variance_detected` | Inbound unit cost varies abnormally vs history |

Minimum inventory `properties`: `location_id`, `country` (`CO`/`US`), `product_id`, `product_category`, `quantity`, `unit`, `currency` (`COP`/`USD`); waste also `reason`. No employee names or customer data.

## Business constraints

- Record amounts in local currency; do not convert in the telemetry layer.
- Stock changes only via inbound/outbound orders, traceable to a user.
- UI language events are independent from location `country`.

See also: `docs/telemetry/telemetry-plan.md` and `docs/telemetry/event-schemas.json`.
