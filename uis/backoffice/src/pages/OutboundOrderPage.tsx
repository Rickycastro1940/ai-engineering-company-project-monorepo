import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FetchError, Spinner } from "../components/AsyncState";
import {
  createOutboundOrder,
  getInventoryProduct,
  inventoryErrorMessage,
  listInventory,
  type InventoryProduct,
} from "../lib/inventory";
import "./AuthPages.css";
import "./AccessiblePage.css";

function asProductList(value: unknown): InventoryProduct[] {
  return Array.isArray(value) ? value : [];
}

function currentStockOf(product: InventoryProduct | null): number | null {
  if (!product) {
    return null;
  }
  const stock = product.current_stock ?? product.quantity;
  return Number.isFinite(Number(stock)) ? Number(stock) : null;
}

export function OutboundOrderPage() {
  const [searchParams] = useSearchParams();
  const preselectedId = searchParams.get("product_id") ?? "";

  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [listStatus, setListStatus] = useState<"loading" | "success" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [listNonce, setListNonce] = useState(0);

  const [productId, setProductId] = useState(preselectedId);
  const [selectedStock, setSelectedStock] = useState<InventoryProduct | null>(null);
  const [stockStatus, setStockStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [stockError, setStockError] = useState<string | null>(null);

  const [quantity, setQuantity] = useState("");
  const [quantityError, setQuantityError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const retryList = useCallback(() => {
    setListNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setListStatus("loading");
    setLoadError(null);

    void (async () => {
      try {
        const rows = asProductList(await listInventory());
        if (cancelled) {
          return;
        }
        setProducts(rows);
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setProducts([]);
          setLoadError(
            inventoryErrorMessage(err, "Ingredients could not be loaded for kitchen usage."),
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
    const selectedId = Number.parseInt(productId, 10);
    if (!productId || !Number.isFinite(selectedId) || selectedId < 1) {
      setSelectedStock(null);
      setStockStatus("idle");
      setStockError(null);
      return;
    }

    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setStockStatus("loading");
    setStockError(null);
    setQuantityError(null);

    void (async () => {
      try {
        const product = await getInventoryProduct(selectedId);
        if (cancelled) {
          return;
        }
        setSelectedStock(product);
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setSelectedStock(null);
          setStockError(inventoryErrorMessage(err, "Current stock could not be loaded for that ingredient."));
        }
      } finally {
        if (!cancelled) {
          setStockStatus(outcome);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [productId]);

  const onHand = currentStockOf(selectedStock);
  const parsedQuantity = Number.parseInt(quantity, 10);
  const exceedsStock = useMemo(() => {
    if (onHand == null || !Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      return false;
    }
    return parsedQuantity > onHand;
  }, [onHand, parsedQuantity]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    setQuantityError(null);

    const selectedId = Number.parseInt(productId, 10);
    if (!selectedStock || !Number.isFinite(selectedId)) {
      setFormError("Choose an ingredient by name.");
      return;
    }
    if (!Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      setQuantityError("Enter a positive whole number for kitchen usage.");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await createOutboundOrder({
        product_id: selectedStock.product_id,
        quantity: parsedQuantity,
      });
      setQuantity("");
      setQuantityError(null);
      setSelectedStock(result.product);
      setStockStatus("success");
      setFormSuccess(
        `Kitchen usage recorded for ${result.product.name}: −${result.quantity} ${result.product.unit}. Current stock is now ${currentStockOf(result.product)} ${result.product.unit}.`,
      );
    } catch (err: unknown) {
      const message = inventoryErrorMessage(err, "That kitchen usage could not be recorded.");
      if (/insufficient stock/i.test(message) || /cannot reduce below 0/i.test(message)) {
        setQuantityError(message);
      } else {
        setFormError(message);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="accessible" aria-labelledby="outbound-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="outbound-title">Kitchen usage</h2>
        <p className="accessible__lead">
          Record kitchen usage leaving current stock at a Brasaland location.
          Current stock loads when you pick an ingredient. Usage that would cause
          a stockout below 0 is rejected.{" "}
          <Link to="/inventory/products">Back to current stock</Link>
          {" · "}
          <Link to="/inventory/orders">Ingredient orders</Link>
        </p>
      </div>

      <div className="accessible__panel auth-card--embedded">
        {listStatus === "loading" ? <Spinner label="Loading ingredients…" /> : null}
        {listStatus === "error" ? (
          <FetchError
            message={loadError || "Ingredients could not be loaded."}
            onRetry={retryList}
            homeTo="/inventory/products"
            homeLabel="Current stock"
          />
        ) : null}
        {listStatus === "success" ? (
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <label>
              Ingredient
              <select
                name="product_id"
                value={productId}
                onChange={(event) => {
                  setProductId(event.target.value);
                  setFormSuccess(null);
                  setFormError(null);
                  setQuantityError(null);
                }}
                required
              >
                <option value="">Select an ingredient</option>
                {products.map((product) => (
                  <option key={product.product_id} value={String(product.product_id)}>
                    {product.name}
                  </option>
                ))}
              </select>
            </label>

            <p className="auth-meta outbound-stock" aria-live="polite">
              <span className="outbound-stock__label">Current stock</span>
              {stockStatus === "idle" ? (
                <span className="outbound-stock__value">Select an ingredient to load current stock.</span>
              ) : null}
              {stockStatus === "loading" ? (
                <span className="outbound-stock__value">Loading current stock…</span>
              ) : null}
              {stockStatus === "error" ? (
                <span className="auth-form__error">{stockError}</span>
              ) : null}
              {stockStatus === "success" && selectedStock && onHand != null ? (
                <span className="outbound-stock__value">
                  <strong>{onHand}</strong> {selectedStock.unit} on hand
                  {selectedStock.name ? ` · ${selectedStock.name}` : ""}
                </span>
              ) : null}
            </p>

            <label>
              Kitchen usage quantity
              <input
                type="number"
                min={1}
                step={1}
                name="quantity"
                value={quantity}
                onChange={(event) => {
                  setQuantity(event.target.value);
                  setQuantityError(null);
                }}
                required
              />
              {exceedsStock && onHand != null ? (
                <span className="auth-form__warning">
                  That quantity is higher than current stock ({onHand}{" "}
                  {selectedStock?.unit}). You can still submit — a stockout below
                  0 will be rejected.
                </span>
              ) : null}
              {quantityError ? (
                <span className="auth-form__error" role="alert">
                  {quantityError}
                </span>
              ) : null}
            </label>
            {formError ? (
              <p className="auth-form__error" role="alert">
                {formError}
              </p>
            ) : null}
            {formSuccess ? (
              <p className="auth-form__success" role="status">
                {formSuccess}
              </p>
            ) : null}
            <button type="submit" disabled={isSubmitting || products.length === 0}>
              {isSubmitting ? "Recording kitchen usage…" : "Record kitchen usage"}
            </button>
          </form>
        ) : null}
      </div>
    </section>
  );
}
