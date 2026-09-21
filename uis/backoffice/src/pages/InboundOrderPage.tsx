import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FetchError, Spinner } from "../components/AsyncState";
import {
  createInboundOrder,
  inventoryErrorMessage,
  listInventory,
  type InventoryProduct,
} from "../lib/inventory";
import "./AuthPages.css";
import "./AccessiblePage.css";

function asProductList(value: unknown): InventoryProduct[] {
  return Array.isArray(value) ? value : [];
}

export function InboundOrderPage() {
  const [searchParams] = useSearchParams();
  const preselectedId = searchParams.get("product_id") ?? "";

  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const [productId, setProductId] = useState(preselectedId);
  const [quantity, setQuantity] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const retry = useCallback(() => {
    setNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setStatus("loading");
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
            inventoryErrorMessage(err, "Kitchen products could not be loaded for an inbound order."),
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    const selectedId = Number.parseInt(productId, 10);
    const parsedQuantity = Number.parseInt(quantity, 10);
    const selected = products.find((item) => item.product_id === selectedId);

    if (!selected) {
      setFormError("Choose a kitchen product by name.");
      return;
    }
    if (!Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      setFormError("Enter a positive whole number for the inbound delivery quantity.");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await createInboundOrder({
        product_id: selected.product_id,
        quantity: parsedQuantity,
      });
      setProductId("");
      setQuantity("");
      setFormSuccess(
        `Inbound order recorded for ${result.product.name}: +${result.quantity} ${result.product.unit}. On-hand stock is now ${result.product.quantity} ${result.product.unit}.`,
      );
    } catch (err: unknown) {
      setFormError(inventoryErrorMessage(err, "That inbound order could not be recorded."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="accessible" aria-labelledby="inbound-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="inbound-title">Inbound ingredient order</h2>
        <p className="accessible__lead">
          Record a supplier delivery into kitchen stock for the 14 Brasaland locations
          — the replacement for WhatsApp inbound orders. Choose the product by name.{" "}
          <Link to="/inventory/products">Back to kitchen products</Link>
          {" · "}
          <Link to="/inventory/orders">Order history</Link>
        </p>
      </div>

      <div className="accessible__panel auth-card--embedded">
        {status === "loading" ? <Spinner label="Loading kitchen products…" /> : null}
        {status === "error" ? (
          <FetchError
            message={loadError || "Kitchen products could not be loaded."}
            onRetry={retry}
            homeTo="/inventory/products"
            homeLabel="Kitchen products"
          />
        ) : null}
        {status === "success" ? (
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <label>
              Kitchen product
              <select
                name="product_id"
                value={productId}
                onChange={(event) => setProductId(event.target.value)}
                required
              >
                <option value="">Select a product</option>
                {products.map((product) => (
                  <option key={product.product_id} value={String(product.product_id)}>
                    {product.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Inbound quantity
              <input
                type="number"
                min={1}
                step={1}
                name="quantity"
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                required
              />
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
              {isSubmitting ? "Recording inbound order…" : "Submit inbound order"}
            </button>
          </form>
        ) : null}
      </div>
    </section>
  );
}
