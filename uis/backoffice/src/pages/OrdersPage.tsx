import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AsyncPanel } from "../components/AsyncState";
import {
  inventoryErrorMessage,
  listInventoryOrders,
  type InventoryOrder,
} from "../lib/inventory";
import { supplyMovementLabel } from "../lib/stockLevels";
import "./AccessiblePage.css";
import "./ProductsPage.css";
import "./OrdersPage.css";

function asOrderList(value: unknown): InventoryOrder[] {
  return Array.isArray(value) ? value : [];
}

function formatCreatedAt(value: string | undefined): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function orderKind(orderType: string | undefined): "inbound" | "outbound" | "other" {
  if (orderType === "inbound") {
    return "inbound";
  }
  if (orderType === "outbound") {
    return "outbound";
  }
  return "other";
}

export function OrdersPage() {
  const [orders, setOrders] = useState<InventoryOrder[] | null>(null);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const retry = useCallback(() => {
    setNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setStatus("loading");
    setError(null);

    void (async () => {
      try {
        const rows = asOrderList(await listInventoryOrders());
        if (cancelled) {
          return;
        }
        setOrders(rows);
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setOrders(null);
          setError(
            inventoryErrorMessage(
              err,
              "Ingredient orders could not be loaded. Try again in a moment.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setStatus(outcome);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [nonce]);

  const rows = orders ?? [];

  return (
    <section className="accessible orders" aria-labelledby="orders-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="orders-title">Ingredient orders</h2>
        <p className="accessible__lead">
          Read-only log of supply orders for the 14 Brasaland kitchens — ingredient,
          quantity, supplier delivery vs kitchen usage, when it was recorded, and
          which kitchen staff recorded it. This replaces WhatsApp and phone
          ingredient orders so Felipe Guerrero can see stockouts and overstock
          across Colombia and Florida. There are no edit or delete actions here.
        </p>
        <p className="accessible__link-row">
          <Link to="/inventory/orders/inbound">Record a supplier delivery</Link>
          {" · "}
          <Link to="/inventory/orders/outbound">Record kitchen usage</Link>
          {" · "}
          <Link to="/inventory/products">Current stock</Link>
        </p>
      </div>

      <div className="accessible__panel">
        <h3>Supply orders for all locations</h3>
        <ul className="products__legend" aria-label="Supply movement key">
          <li>
            <span className="orders__badge orders__badge--inbound">Supplier delivery</span>
            Stock arriving from Lucía Fernández’s suppliers
          </li>
          <li>
            <span className="orders__badge orders__badge--outbound">Kitchen usage</span>
            Stock leaving a location kitchen
          </li>
        </ul>
        <AsyncPanel
          status={status}
          loadingLabel="Loading ingredient orders…"
          error={error}
          onRetry={retry}
          skeletonRows={6}
        >
          {rows.length === 0 ? (
            <p className="accessible__status">
              No ingredient orders recorded yet. Record a{" "}
              <Link to="/inventory/orders/inbound">supplier delivery</Link> or{" "}
              <Link to="/inventory/orders/outbound">kitchen usage</Link> to
              start the audit trail.
            </p>
          ) : (
            <div className="accessible__table-wrap inventory__table-wrap">
              <table className="accessible__table orders__table">
                <thead>
                  <tr>
                    <th scope="col">Ingredient</th>
                    <th scope="col">Quantity</th>
                    <th scope="col">Supply movement</th>
                    <th scope="col">Recorded</th>
                    <th scope="col">
                      Kitchen staff <code>user_uuid</code>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((order, index) => {
                    const kind = orderKind(order.order_type);
                    const quantityLabel = order.unit
                      ? `${order.quantity} ${order.unit}`
                      : String(order.quantity ?? "—");
                    return (
                      <tr
                        key={order.order_id ?? `${order.product_name}-${order.created_at}-${index}`}
                        className={`orders__row orders__row--${kind}`}
                      >
                        <td>{order.product_name ?? "Unnamed ingredient"}</td>
                        <td className="orders__qty">{quantityLabel}</td>
                        <td>
                          <span className={`orders__badge orders__badge--${kind}`}>
                            <span className="orders__icon" aria-hidden="true">
                              {kind === "inbound" ? "↓" : kind === "outbound" ? "↑" : "•"}
                            </span>
                            {supplyMovementLabel(order.order_type)}
                          </span>
                        </td>
                        <td>{formatCreatedAt(order.created_at)}</td>
                        <td className="orders__uuid">{order.user_uuid || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </AsyncPanel>
      </div>
    </section>
  );
}
