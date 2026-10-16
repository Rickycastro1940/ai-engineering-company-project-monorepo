import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { FetchError, Spinner } from "../components/AsyncState";
import {
  createInboundOrder,
  inventoryErrorMessage,
  KITCHEN_LOCATIONS,
  listInventory,
  type InventoryProduct,
} from "../lib/inventory";
import { currentStockOf } from "../lib/stockLevels";
import "./AuthPages.css";
import "./AccessiblePage.css";

function asProductList(value: unknown): InventoryProduct[] {
  return Array.isArray(value) ? value : [];
}

export function InboundOrderPage() {
  const [searchParams] = useSearchParams();
  const preselectedId = searchParams.get("ingredient_id") ?? searchParams.get("product_id") ?? "";

  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const [ingredientId, setIngredientId] = useState(preselectedId);
  const [quantity, setQuantity] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [locationId, setLocationId] = useState("1");
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
            inventoryErrorMessage(err, "Ingredients could not be loaded for a supplier delivery."),
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

    const selectedId = Number.parseInt(ingredientId, 10);
    const parsedQuantity = Number.parseFloat(quantity);
    const parsedLocation = Number.parseInt(locationId, 10);
    const selected = products.find((item) => item.id === selectedId);

    if (!selected) {
      setFormError("Choose an ingredient by name.");
      return;
    }
    if (!Number.isFinite(parsedQuantity) || parsedQuantity <= 0) {
      setFormError("Enter a positive quantity for the supplier delivery.");
      return;
    }
    if (!supplierName.trim()) {
      setFormError("Enter the supplier name for this delivery.");
      return;
    }
    if (!Number.isFinite(parsedLocation) || parsedLocation < 1 || parsedLocation > 14) {
      setFormError("Choose one of Brasaland’s 14 kitchen locations.");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await createInboundOrder({
        ingredient_id: selected.id,
        quantity: parsedQuantity,
        supplier_name: supplierName.trim(),
        location_id: parsedLocation,
      });
      const refreshed = await listInventory();
      setProducts(asProductList(refreshed));
      const updated = asProductList(refreshed).find((item) => item.id === selected.id);
      const onHand = currentStockOf(updated ?? null);
      setIngredientId("");
      setQuantity("");
      setSupplierName("");
      setFormSuccess(
        `Supplier delivery recorded for ${result.name || selected.name}: +${result.quantity} ${selected.unit}. Current stock is now ${onHand ?? "—"} ${selected.unit}.`,
      );
    } catch (err: unknown) {
      setFormError(inventoryErrorMessage(err, "That supplier delivery could not be recorded."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="accessible" aria-labelledby="inbound-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="inbound-title">Supplier delivery</h2>
        <p className="accessible__lead">
          Record a delivery from Brasaland’s suppliers into kitchen stock at one of
          the 14 locations — the replacement for WhatsApp ingredient orders. Choose
          the ingredient by name.{" "}
          <Link to="/inventory/products">Back to current stock</Link>
          {" · "}
          <Link to="/inventory/orders">Ingredient orders</Link>
        </p>
      </div>

      <div className="accessible__panel auth-card--embedded">
        {status === "loading" ? <Spinner label="Loading ingredients…" /> : null}
        {status === "error" ? (
          <FetchError
            message={loadError || "Ingredients could not be loaded."}
            onRetry={retry}
            homeTo="/inventory/products"
            homeLabel="Current stock"
          />
        ) : null}
        {status === "success" ? (
          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            <label>
              Ingredient
              <select
                name="ingredient_id"
                value={ingredientId}
                onChange={(event) => setIngredientId(event.target.value)}
                required
              >
                <option value="">Select an ingredient</option>
                {products.map((product) => (
                  <option key={product.id} value={String(product.id)}>
                    {product.name} ({product.sku})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Supplier name
              <input
                type="text"
                name="supplier_name"
                value={supplierName}
                onChange={(event) => setSupplierName(event.target.value)}
                placeholder="e.g. Carnes del Valle S.A."
                required
              />
            </label>
            <label>
              Kitchen location
              <select
                name="location_id"
                value={locationId}
                onChange={(event) => setLocationId(event.target.value)}
                required
              >
                {KITCHEN_LOCATIONS.map((location) => (
                  <option key={location.id} value={String(location.id)}>
                    {location.name} · {location.market}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Delivery quantity
              <input
                type="number"
                min={0.01}
                step="any"
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
              {isSubmitting ? "Recording supplier delivery…" : "Record supplier delivery"}
            </button>
          </form>
        ) : null}
      </div>
    </section>
  );
}
