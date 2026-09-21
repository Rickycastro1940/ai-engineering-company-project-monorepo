import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { AsyncPanel } from "../components/AsyncState";
import {
  createInventoryProduct,
  fetchInventory,
  fetchInventoryAlerts,
  inventoryApiBaseUrl,
  inventoryErrorMessage,
  updateInventoryStock,
  type InventoryProduct,
} from "../lib/inventory";
import "./AuthPages.css";
import "./AccessiblePage.css";
import "./InventoryPage.css";

const DEFAULT_ALERT_THRESHOLD = 10;

function asProductList(value: unknown): InventoryProduct[] {
  return Array.isArray(value) ? value : [];
}

export function InventoryPage() {
  const [products, setProducts] = useState<InventoryProduct[] | null>(null);
  const [alerts, setAlerts] = useState<InventoryProduct[] | null>(null);
  const [listStatus, setListStatus] = useState<"loading" | "success" | "error">("loading");
  const [alertStatus, setAlertStatus] = useState<"loading" | "success" | "error">("loading");
  const [listError, setListError] = useState<string | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);
  const [listNonce, setListNonce] = useState(0);
  const [alertNonce, setAlertNonce] = useState(0);
  const [threshold, setThreshold] = useState(DEFAULT_ALERT_THRESHOLD);
  const [appliedThreshold, setAppliedThreshold] = useState(DEFAULT_ALERT_THRESHOLD);

  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("0");
  const [unit, setUnit] = useState("kg");
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const [deltaById, setDeltaById] = useState<Record<number, string>>({});
  const [rowBusyId, setRowBusyId] = useState<number | null>(null);
  const [stockMessage, setStockMessage] = useState<string | null>(null);
  const [stockError, setStockError] = useState<string | null>(null);

  const retryList = useCallback(() => {
    setListNonce((value) => value + 1);
  }, []);

  const retryAlerts = useCallback(() => {
    setAlertNonce((value) => value + 1);
  }, []);

  const refreshAll = useCallback(() => {
    setListNonce((value) => value + 1);
    setAlertNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setListStatus("loading");
    setListError(null);

    void (async () => {
      try {
        const inventoryData = await fetchInventory();
        if (cancelled) {
          return;
        }
        setProducts(asProductList(inventoryData));
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setProducts(null);
          setListError(
            inventoryErrorMessage(
              err,
              "Kitchen inventory could not be loaded. Try again in a moment.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setListStatus(outcome);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [listNonce]);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setAlertStatus("loading");
    setAlertError(null);

    void (async () => {
      try {
        const alertData = await fetchInventoryAlerts(appliedThreshold);
        if (cancelled) {
          return;
        }
        setAlerts(asProductList(alertData));
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setAlerts(null);
          setAlertError(
            inventoryErrorMessage(
              err,
              "Low-stock alerts could not be loaded. Try again in a moment.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setAlertStatus(outcome);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [alertNonce, appliedThreshold]);

  const stock = products ?? [];
  const lowStock = alerts ?? [];
  const lowStockIds = useMemo(
    () => new Set(lowStock.map((item) => item.product_id)),
    [lowStock],
  );
  const apiBase = inventoryApiBaseUrl();

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    const trimmedName = name.trim();
    const trimmedUnit = unit.trim();
    const parsedQuantity = Number.parseInt(quantity, 10);

    if (!trimmedName) {
      setFormError("Enter a product name used in the kitchen.");
      return;
    }
    if (!trimmedUnit) {
      setFormError("Enter a unit (kg, boxes, liters, portions).");
      return;
    }
    if (!Number.isFinite(parsedQuantity) || parsedQuantity < 0) {
      setFormError("On-hand quantity must be zero or a positive whole number.");
      return;
    }

    setIsCreating(true);
    try {
      const created = await createInventoryProduct({
        name: trimmedName,
        quantity: parsedQuantity,
        unit: trimmedUnit,
      });
      setName("");
      setQuantity("0");
      setUnit("kg");
      setFormSuccess(`${created.name} was added to kitchen inventory.`);
      refreshAll();
    } catch (err: unknown) {
      setFormError(inventoryErrorMessage(err, "That product could not be added. Try again."));
    } finally {
      setIsCreating(false);
    }
  }

  async function handleStockChange(product: InventoryProduct, direction: "in" | "out") {
    setStockError(null);
    setStockMessage(null);
    const raw = deltaById[product.product_id] ?? "1";
    const amount = Number.parseInt(raw, 10);
    if (!Number.isFinite(amount) || amount <= 0) {
      setStockError("Enter a positive whole number for incoming or outgoing stock.");
      return;
    }

    const delta = direction === "in" ? amount : -amount;

    setRowBusyId(product.product_id);
    try {
      const updated = await updateInventoryStock(product.product_id, delta);
      setStockMessage(
        direction === "in"
          ? `Incoming delivery recorded for ${updated.name}. On hand: ${updated.quantity} ${updated.unit}.`
          : `Kitchen usage recorded for ${updated.name}. On hand: ${updated.quantity} ${updated.unit}.`,
      );
      refreshAll();
    } catch (err: unknown) {
      setStockError(inventoryErrorMessage(err, "Stock could not be updated. Try again."));
    } finally {
      setRowBusyId(null);
    }
  }

  function applyThreshold() {
    const parsed = Number.parseInt(String(threshold), 10);
    if (!Number.isFinite(parsed) || parsed < 0) {
      setAlertError("Alert threshold must be zero or greater.");
      return;
    }
    setAppliedThreshold(parsed);
  }

  return (
    <section className="accessible inventory" aria-labelledby="inventory-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="inventory-title">Kitchen inventory</h2>
        <p className="accessible__lead">
          Ingredient stock for Brasaland kitchens — the same product names, on-hand{" "}
          <strong>quantity</strong>, and <strong>unit</strong> the central API stores in{" "}
          <code>products.csv</code>. This view replaces WhatsApp and phone orders with
          on-hand data so supervisors can see stockouts before they hit a location in
          Colombia or Florida.
        </p>
        <p className="inventory__api-hint">
          Inventory API: <code>{apiBase || "(same origin / Vite proxy)"}</code>
        </p>
      </div>

      <div className="inventory__layout">
        <div className="accessible__panel">
          <h3>Add kitchen product</h3>
          <p className="inventory__help">
            Fields match <code>POST /inventory</code>: product name, on-hand quantity, and
            unit (kg, boxes, liters).
          </p>
          <form className="auth-form inventory__form" onSubmit={handleCreate}>
            <label>
              Product name
              <input
                name="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Tomatoes"
                autoComplete="off"
              />
            </label>
            <div className="inventory__form-row">
              <label>
                On-hand quantity
                <input
                  name="quantity"
                  type="number"
                  min={0}
                  step={1}
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </label>
              <label>
                Unit
                <input
                  name="unit"
                  value={unit}
                  onChange={(event) => setUnit(event.target.value)}
                  placeholder="kg"
                  autoComplete="off"
                />
              </label>
            </div>
            {formError ? <p className="auth-form__error">{formError}</p> : null}
            {formSuccess ? <p className="auth-form__success">{formSuccess}</p> : null}
            <button type="submit" disabled={isCreating}>
              {isCreating ? "Adding product…" : "Add product"}
            </button>
          </form>
        </div>

        <div className="accessible__panel">
          <h3>Low-stock alerts</h3>
          <p className="inventory__help">
            Products below the alert threshold (<code>GET /inventory/alerts</code>).
            Default threshold is 10 — the same rule the inventory agent uses.
          </p>
          <div className="inventory__threshold">
            <label>
              Alert threshold
              <input
                type="number"
                min={0}
                step={1}
                value={threshold}
                onChange={(event) => setThreshold(Number.parseInt(event.target.value, 10) || 0)}
              />
            </label>
            <button type="button" className="inventory__secondary" onClick={applyThreshold}>
              Refresh alerts
            </button>
          </div>
          <AsyncPanel
            status={alertStatus}
            loadingLabel="Loading low-stock alerts…"
            error={alertError}
            onRetry={retryAlerts}
            skeletonRows={3}
          >
            {lowStock.length === 0 ? (
              <p className="accessible__status">
                No products are below {appliedThreshold} on hand.
              </p>
            ) : (
              <ul className="accessible__list">
                {lowStock.map((product, index) => (
                  <li key={product.product_id ?? `${product.name}-${index}`}>
                    <span className="accessible__loc-name">{product.name}</span>
                    <span className="accessible__loc-meta">
                      {product.quantity} {product.unit} on hand · product_id {product.product_id}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </AsyncPanel>
        </div>

        <div className="accessible__panel accessible__panel--span">
          <h3>On-hand kitchen stock</h3>
          <p className="inventory__help">
            Incoming deliveries add stock; kitchen usage subtracts it (
            <code>PATCH /inventory/{"{product_id}"}</code> with a <code>delta</code>). Quantity
            cannot go below 0.
          </p>
          {stockMessage ? <p className="auth-form__success">{stockMessage}</p> : null}
          {stockError ? <p className="auth-form__error">{stockError}</p> : null}
          <AsyncPanel
            status={listStatus}
            loadingLabel="Loading kitchen inventory…"
            error={listError}
            onRetry={retryList}
            skeletonRows={6}
          >
            {stock.length === 0 ? (
              <p className="accessible__status">
                No kitchen products yet. Add beef, produce, sauces, or packaging so
                locations stop ordering blind.
              </p>
            ) : (
              <div className="accessible__table-wrap inventory__table-wrap">
                <table className="accessible__table">
                  <thead>
                    <tr>
                      <th scope="col">Product</th>
                      <th scope="col">On-hand quantity</th>
                      <th scope="col">Unit</th>
                      <th scope="col">Incoming / outgoing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stock.map((product, index) => {
                      const id = product.product_id;
                      const busy = rowBusyId === id;
                      const isAlert = lowStockIds.has(id);
                      return (
                        <tr
                          key={id ?? `${product.name}-${index}`}
                          className={isAlert ? "inventory__row--alert" : undefined}
                        >
                          <td>
                            {product.name}
                            {isAlert ? (
                              <span className="inventory__pill">Below threshold</span>
                            ) : null}
                          </td>
                          <td>{product.quantity}</td>
                          <td>{product.unit}</td>
                          <td>
                            <div className="inventory__delta">
                              <label className="inventory__delta-label">
                                Amount
                                <input
                                  type="number"
                                  min={1}
                                  step={1}
                                  value={deltaById[id] ?? "1"}
                                  onChange={(event) =>
                                    setDeltaById((current) => ({
                                      ...current,
                                      [id]: event.target.value,
                                    }))
                                  }
                                  disabled={busy}
                                />
                              </label>
                              <button
                                type="button"
                                className="inventory__in"
                                disabled={busy}
                                onClick={() => void handleStockChange(product, "in")}
                              >
                                Incoming
                              </button>
                              <button
                                type="button"
                                className="inventory__out"
                                disabled={busy}
                                onClick={() => void handleStockChange(product, "out")}
                              >
                                Outgoing
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </AsyncPanel>
        </div>
      </div>
    </section>
  );
}
