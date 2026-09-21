import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AsyncPanel } from "../components/AsyncState";
import {
  inventoryErrorMessage,
  listInventoryOrders,
  type InventoryOrder,
} from "../lib/inventory";
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
              "Ingredient order history could not be loaded. Try again in a moment.",
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
        <h2 id="orders-title">Ingredient order history</h2>
        <p className="accessible__lead">
          Read-only movement log from <code>GET /inventory/orders</code> — product,
          quantity, inbound vs outbound, creation date, and the staff{" "}
          <code>user_uuid</code> who recorded it. This is the audit trail for
          kitchen stock instead of WhatsApp ingredient orders across the 14
          Brasaland locations. There are no edit or delete actions on this page.
        </p>
        <p className="accessible__link-row">
          <Link to="/inventory/orders/inbound">Record inbound</Link>
          {" · "}
          <Link to="/inventory/orders/outbound">Record outbound</Link>
          {" · "}
          <Link to="/inventory/products">Kitchen products</Link>
        </p>
      </div>

      <div className="accessible__panel">
        <h3>All recorded orders</h3>
        <ul className="products__legend" aria-label="Order type key">
          <li>
            <span className="orders__badge orders__badge--inbound">Inbound</span>
            Supplier delivery into kitchen stock
          </li>
          <li>
            <span className="orders__badge orders__badge--outbound">Outbound</span>
            Kitchen usage leaving stock
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
              No ingredient orders recorded yet. Use{" "}
              <Link to="/inventory/orders/inbound">inbound</Link> or{" "}
              <Link to="/inventory/orders/outbound">outbound</Link> to create the
              first movement.
            </p>
          ) : (
            <div className="accessible__table-wrap inventory__table-wrap">
              <table className="accessible__table orders__table">
                <thead>
                  <tr>
                    <th scope="col">Product name</th>
                    <th scope="col">Quantity</th>
                    <th scope="col">Order type</th>
                    <th scope="col">Created</th>
                    <th scope="col">user_uuid</th>
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
                        <td>{order.product_name ?? "Unnamed product"}</td>
                        <td className="orders__qty">{quantityLabel}</td>
                        <td>
                          <span className={`orders__badge orders__badge--${kind}`}>
                            <span className="orders__icon" aria-hidden="true">
                              {kind === "inbound" ? "↓" : kind === "outbound" ? "↑" : "•"}
                            </span>
                            {kind === "other" ? order.order_type || "Unknown" : kind}
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
