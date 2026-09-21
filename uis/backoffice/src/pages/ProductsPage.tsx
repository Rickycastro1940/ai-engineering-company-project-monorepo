import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AsyncPanel } from "../components/AsyncState";
import {
  inventoryErrorMessage,
  listInventory,
  type InventoryProduct,
} from "../lib/inventory";
import {
  inboundOrderPath,
  outboundOrderPath,
  stockLevelForQuantity,
  stockLevelLabel,
} from "../lib/stockLevels";
import "./AccessiblePage.css";
import "./ProductsPage.css";

function asProductList(value: unknown): InventoryProduct[] {
  return Array.isArray(value) ? value : [];
}

export function ProductsPage() {
  const [products, setProducts] = useState<InventoryProduct[] | null>(null);
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
        const inventoryData = await listInventory();
        if (cancelled) {
          return;
        }
        setProducts(asProductList(inventoryData));
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setProducts(null);
          setError(
            inventoryErrorMessage(
              err,
              "Current kitchen stock could not be loaded. Try again in a moment.",
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

  const rows = products ?? [];

  return (
    <section className="accessible products" aria-labelledby="products-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="products-title">Current kitchen stock</h2>
        <p className="accessible__lead">
          Ingredients and supplies on hand at Brasaland kitchens — meat, vegetables,
          packaging, cleaning products — so the 14 locations stop placing ingredient
          orders on WhatsApp. Color bands flag the stockouts and overstock Felipe
          Guerrero sees when locations order blind.
        </p>
      </div>

      <div className="accessible__panel">
        <h3>Ingredients on hand</h3>
        <ul className="products__legend" aria-label="Stock-level key">
          <li>
            <span className="products__dot products__dot--stockout" aria-hidden="true" />
            Stockout (0)
          </li>
          <li>
            <span className="products__dot products__dot--low" aria-hidden="true" />
            Low (1–9)
          </li>
          <li>
            <span className="products__dot products__dot--healthy" aria-hidden="true" />
            Healthy (10–99)
          </li>
          <li>
            <span className="products__dot products__dot--overstock" aria-hidden="true" />
            Overstock (100+)
          </li>
        </ul>
        <AsyncPanel
          status={status}
          loadingLabel="Loading current kitchen stock…"
          error={error}
          onRetry={retry}
          skeletonRows={6}
        >
          {rows.length === 0 ? (
            <p className="accessible__status">
              No ingredients on the list yet. Add meat, produce, sauces, or
              packaging on <Link to="/inventory">kitchen stock</Link>.
            </p>
          ) : (
            <div className="accessible__table-wrap inventory__table-wrap">
              <table className="accessible__table products__table">
                <thead>
                  <tr>
                    <th scope="col">Ingredient</th>
                    <th scope="col">Current stock</th>
                    <th scope="col">Unit</th>
                    <th scope="col">Stock level</th>
                    <th scope="col">Supply orders</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((product, index) => {
                    const id = product.product_id;
                    const level = stockLevelForQuantity(Number(product.quantity));
                    return (
                      <tr
                        key={id ?? `${product.name}-${index}`}
                        className={`products__row products__row--${level}`}
                      >
                        <td>{product.name ?? "Unnamed ingredient"}</td>
                        <td className="products__on-hand">
                          {product.quantity ?? "—"}
                        </td>
                        <td>{product.unit ?? "—"}</td>
                        <td>
                          <span className={`products__level products__level--${level}`}>
                            <span className={`products__dot products__dot--${level}`} aria-hidden="true" />
                            {stockLevelLabel(level)}
                          </span>
                        </td>
                        <td>
                          <div className="products__orders">
                            <Link className="products__order products__order--in" to={inboundOrderPath(id)}>
                              Record supplier delivery
                            </Link>
                            <Link className="products__order products__order--out" to={outboundOrderPath(id)}>
                              Record kitchen usage
                            </Link>
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
    </section>
  );
}
