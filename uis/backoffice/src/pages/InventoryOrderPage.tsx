import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FetchError, Spinner } from "../components/AsyncState";
import {
  inventoryErrorMessage,
  listInventory,
  updateInventoryStock,
  type InventoryProduct,
} from "../lib/inventory";
import "./AuthPages.css";
import "./AccessiblePage.css";

function parseDirection(value: string | null): "inbound" | "outbound" {
  return value === "outbound" ? "outbound" : "inbound";
}

export function InventoryOrderPage() {
  const [searchParams] = useSearchParams();
  const productId = Number.parseInt(searchParams.get("product_id") ?? "", 10);
  const direction = parseDirection(searchParams.get("direction"));

  const [product, setProduct] = useState<InventoryProduct | null>(null);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [amount, setAmount] = useState("1");
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
    setError(null);
    setProduct(null);

    void (async () => {
      try {
        if (!Number.isFinite(productId) || productId < 1) {
          throw new Error("Choose an ingredient from current stock before recording a supply order.");
        }
        const rows = await listInventory();
        const match = Array.isArray(rows)
          ? rows.find((row) => row.product_id === productId)
          : undefined;
        if (!match) {
          throw new Error(`Ingredient ${productId} was not found in kitchen stock.`);
        }
        if (cancelled) {
          return;
        }
        setProduct(match);
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            inventoryErrorMessage(
              err,
              "That ingredient could not be loaded for a supply order.",
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
  }, [nonce, productId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    if (!product) {
      return;
    }
    const parsed = Number.parseInt(amount, 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setFormError("Enter a positive whole number for this ingredient order.");
      return;
    }
    const delta = direction === "inbound" ? parsed : -parsed;
    setIsSubmitting(true);
    try {
      const updated = await updateInventoryStock(product.product_id, delta);
      setProduct(updated);
      setFormSuccess(
        direction === "inbound"
          ? `Supplier delivery recorded for ${updated.name}. Current stock is now ${updated.quantity} ${updated.unit}.`
          : `Kitchen usage recorded for ${updated.name}. Current stock is now ${updated.quantity} ${updated.unit}.`,
      );
    } catch (err: unknown) {
      setFormError(inventoryErrorMessage(err, "That supply order could not be recorded."));
    } finally {
      setIsSubmitting(false);
    }
  }

  const title = direction === "inbound" ? "Record a supplier delivery" : "Record kitchen usage";

  return (
    <section className="accessible" aria-labelledby="order-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="order-title">{title}</h2>
        <p className="accessible__lead">
          {direction === "inbound"
            ? "Record a supplier delivery into kitchen stock (replaces WhatsApp ingredient orders)."
            : "Record kitchen usage leaving current stock. Quantity cannot go below 0 (stockout)."}{" "}
          <Link to="/inventory/products">Back to current stock</Link>
        </p>
      </div>

      <div className="accessible__panel auth-card--embedded">
        {status === "loading" ? <Spinner label="Loading ingredient…" /> : null}
        {status === "error" ? (
          <FetchError
            message={error || "That ingredient could not be loaded."}
            onRetry={retry}
            homeTo="/inventory/products"
            homeLabel="Current stock"
          />
        ) : null}
        {status === "success" && product ? (
          <>
            <dl className="auth-meta">
              <div>
                <dt>Ingredient</dt>
                <dd>{product.name}</dd>
              </div>
              <div>
                <dt>Current stock</dt>
                <dd>
                  {product.quantity} {product.unit}
                </dd>
              </div>
            </dl>
            <form className="auth-form" onSubmit={handleSubmit}>
              <label>
                Supply quantity ({product.unit})
                <input
                  type="number"
                  min={1}
                  step={1}
                  name="amount"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </label>
              {formError ? <p className="auth-form__error">{formError}</p> : null}
              {formSuccess ? <p className="auth-form__success">{formSuccess}</p> : null}
              <button type="submit" disabled={isSubmitting}>
                {isSubmitting
                  ? "Recording supply order…"
                  : direction === "inbound"
                    ? "Record supplier delivery"
                    : "Record kitchen usage"}
              </button>
            </form>
          </>
        ) : null}
      </div>
    </section>
  );
}
