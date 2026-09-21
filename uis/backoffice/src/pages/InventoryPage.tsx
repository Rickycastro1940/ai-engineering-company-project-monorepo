import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
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
              "Kitchen stock could not be loaded. Try again in a moment.",
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
      setFormError("Enter an ingredient name used in the kitchen.");
      return;
    }
    if (!trimmedUnit) {
      setFormError("Enter a unit (kg, boxes, liters, portions).");
      return;
    }
    if (!Number.isFinite(parsedQuantity) || parsedQuantity < 0) {
      setFormError("Current stock must be zero or a positive whole number.");
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
      setFormSuccess(`${created.name} was added to kitchen stock.`);
      refreshAll();
    } catch (err: unknown) {
      setFormError(inventoryErrorMessage(err, "That ingredient could not be added. Try again."));
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
          ? `Supplier delivery recorded for ${updated.name}. Current stock: ${updated.quantity} ${updated.unit}.`
          : `Kitchen usage recorded for ${updated.name}. Current stock: ${updated.quantity} ${updated.unit}.`,
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
        <h2 id="inventory-title">Kitchen stock</h2>
        <p className="accessible__lead">
          Ingredient stock for Brasaland kitchens — meat, vegetables, sauces,
          packaging, and cleaning products — so supervisors can see stockouts
          before they hit a location in Colombia or Florida. This view replaces
          WhatsApp and phone ingredient orders.{" "}
          <Link to="/inventory/products">Open current stock</Link> for stockout
          and overstock bands, then record a supplier delivery or kitchen usage.
        </p>
        <p className="inventory__api-hint">
          Inventory API: <code>{apiBase || "(same origin / Vite proxy)"}</code>
        </p>
      </div>

      <div className="inventory__layout">
        <div className="accessible__panel">
          <h3>Add an ingredient</h3>
          <p className="inventory__help">
            Name the ingredient or supply, current stock, and unit (kg, boxes,
            liters) used in the kitchen.
          </p>
          <form className="auth-form inventory__form" onSubmit={handleCreate}>
            <label>
              Ingredient
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
                Current stock
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
              {isCreating ? "Adding ingredient…" : "Add ingredient"}
            </button>
          </form>
        </div>

        <div className="accessible__panel">
          <h3>Stockout alerts</h3>
          <p className="inventory__help">
            Ingredients below the alert threshold — the same stockout signal
            supervisors need when a location is about to run out.
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
                No ingredients are below {appliedThreshold} on hand.
              </p>
            ) : (
              <ul className="accessible__list">
                {lowStock.map((product, index) => (
                  <li key={product.product_id ?? `${product.name}-${index}`}>
                    <span className="accessible__loc-name">{product.name}</span>
                    <span className="accessible__loc-meta">
                      {product.quantity} {product.unit} current stock
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </AsyncPanel>
        </div>

        <div className="accessible__panel accessible__panel--span">
          <h3>Current kitchen stock</h3>
          <p className="inventory__help">
            Supplier deliveries add stock; kitchen usage subtracts it. Current
            stock cannot go below 0 — a stockout stops the line.
          </p>
          {stockMessage ? <p className="auth-form__success">{stockMessage}</p> : null}
          {stockError ? <p className="auth-form__error">{stockError}</p> : null}
          <AsyncPanel
            status={listStatus}
            loadingLabel="Loading kitchen stock…"
            error={listError}
            onRetry={retryList}
            skeletonRows={6}
          >
            {stock.length === 0 ? (
              <p className="accessible__status">
                No ingredients yet. Add meat, produce, sauces, or packaging so
                locations stop ordering blind.
              </p>
            ) : (
              <div className="accessible__table-wrap inventory__table-wrap">
                <table className="accessible__table">
                  <thead>
                    <tr>
                      <th scope="col">Ingredient</th>
                      <th scope="col">Current stock</th>
                      <th scope="col">Unit</th>
                      <th scope="col">Supplier delivery / kitchen usage</th>
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
                                Supplier delivery
                              </button>
                              <button
                                type="button"
                                className="inventory__out"
                                disabled={busy}
                                onClick={() => void handleStockChange(product, "out")}
                              >
                                Kitchen usage
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
