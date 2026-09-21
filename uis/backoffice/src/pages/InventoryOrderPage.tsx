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
          throw new Error("Choose a kitchen product from the products list before creating an order.");
        }
        const rows = await listInventory();
        const match = Array.isArray(rows)
          ? rows.find((row) => row.product_id === productId)
          : undefined;
        if (!match) {
          throw new Error(`Kitchen product ${productId} was not found in inventory.`);
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
              "That kitchen product could not be loaded for an ingredient order.",
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
          ? `Inbound supplier order recorded for ${updated.name}. On-hand stock is now ${updated.quantity} ${updated.unit}.`
          : `Outbound kitchen order recorded for ${updated.name}. On-hand stock is now ${updated.quantity} ${updated.unit}.`,
      );
    } catch (err: unknown) {
      setFormError(inventoryErrorMessage(err, "That ingredient order could not be recorded."));
    } finally {
      setIsSubmitting(false);
    }
  }

  const title = direction === "inbound" ? "Create inbound order" : "Create outbound order";

  return (
    <section className="accessible" aria-labelledby="order-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="order-title">{title}</h2>
        <p className="accessible__lead">
          {direction === "inbound"
            ? "Record a supplier delivery into kitchen stock (replaces WhatsApp inbound orders)."
            : "Record kitchen usage leaving on-hand stock (outbound to the line). Quantity cannot go below 0."}{" "}
          <Link to="/inventory/products">Back to kitchen products</Link>
        </p>
      </div>

      <div className="accessible__panel auth-card--embedded">
        {status === "loading" ? <Spinner label="Loading kitchen product…" /> : null}
        {status === "error" ? (
          <FetchError
            message={error || "That kitchen product could not be loaded."}
            onRetry={retry}
            homeTo="/inventory/products"
            homeLabel="Kitchen products"
          />
        ) : null}
        {status === "success" && product ? (
          <>
            <dl className="auth-meta">
              <div>
                <dt>Kitchen product</dt>
                <dd>{product.name}</dd>
              </div>
              <div>
                <dt>On-hand stock</dt>
                <dd>
                  {product.quantity} {product.unit}
                </dd>
              </div>
            </dl>
            <form className="auth-form" onSubmit={handleSubmit}>
              <label>
                Order quantity ({product.unit})
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
                  ? "Recording order…"
                  : direction === "inbound"
                    ? "Record inbound order"
                    : "Record outbound order"}
              </button>
            </form>
          </>
        ) : null}
      </div>
    </section>
  );
}
