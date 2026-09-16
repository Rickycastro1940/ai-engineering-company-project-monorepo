import { useEffect, useState } from "react";
import {
  fetchInventory,
  fetchLocationsOverview,
  type InventoryProduct,
  type LocationsOverview,
} from "../lib/api";
import "./AccessiblePage.css";

export function AccessiblePage() {
  const [overview, setOverview] = useState<LocationsOverview | null>(null);
  const [inventory, setInventory] = useState<InventoryProduct[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [locationData, inventoryData] = await Promise.all([
          fetchLocationsOverview(),
          fetchInventory(),
        ]);
        if (!cancelled) {
          setOverview(locationData);
          setInventory(inventoryData);
        }
      } catch (err) {
        if (!cancelled) {
          setOverview(null);
          setInventory(null);
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load protected operations data",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="accessible" aria-labelledby="accessible-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Protected view</p>
        <h2 id="accessible-title">Brasaland operations entry</h2>
        <p className="accessible__lead">
          Staff console for Felipe Guerrero and Mariana Restrepo. After login,
          this page loads <code>GET /locations/overview</code> (JWT required)
          and <code>GET /inventory</code> with <code>Authorization: Bearer</code>{" "}
          — 14 restaurants across Colombia and Florida, COP and USD.
        </p>
      </div>

      <div className="accessible__dashboard" aria-label="Authenticated operations dashboard">
        <div className="accessible__panel accessible__panel--span">
          <h3>Company footprint</h3>
          {loading && <p className="accessible__status">Loading protected location data…</p>}
          {error && (
            <p className="accessible__error" role="alert">
              {error}. Start the API with{" "}
              <code>uvicorn api.app:app --reload</code> on port 8000 and sign in
              again.
            </p>
          )}
          {overview && (
            <>
              <dl className="accessible__stats">
                <div>
                  <dt>Total locations</dt>
                  <dd>{overview.total_locations}</dd>
                </div>
                <div>
                  <dt>Colombia</dt>
                  <dd>{overview.colombia_count}</dd>
                </div>
                <div>
                  <dt>Florida (US)</dt>
                  <dd>{overview.florida_count}</dd>
                </div>
                <div>
                  <dt>Currencies</dt>
                  <dd className="accessible__currencies">
                    {overview.currencies.map((currency) => (
                      <span
                        key={currency}
                        className={
                          currency === "COP"
                            ? "badge badge--cop"
                            : "badge badge--usd"
                        }
                      >
                        {currency}
                      </span>
                    ))}
                  </dd>
                </div>
              </dl>
              <p className="accessible__source">{overview.source}</p>
            </>
          )}
        </div>

        <div className="accessible__panel">
          <h3>Location roster</h3>
          {overview ? (
            <ul className="accessible__list">
              {overview.locations.map((location) => (
                <li key={location.id}>
                  <span className="accessible__loc-name">{location.name}</span>
                  <span className="accessible__loc-meta">
                    {location.city} · {location.region} ·{" "}
                    <span
                      className={
                        location.currency === "COP"
                          ? "badge badge--cop"
                          : "badge badge--usd"
                      }
                    >
                      {location.currency}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="accessible__status">Waiting for authenticated API data…</p>
          )}
        </div>

        <div className="accessible__panel">
          <h3>Kitchen inventory</h3>
          {loading && <p className="accessible__status">Loading inventory…</p>}
          {inventory && inventory.length === 0 && (
            <p className="accessible__status">No products in products.csv yet.</p>
          )}
          {inventory && inventory.length > 0 && (
            <div className="accessible__table-wrap">
              <table className="accessible__table">
                <thead>
                  <tr>
                    <th scope="col">Product</th>
                    <th scope="col">Quantity</th>
                    <th scope="col">Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {inventory.map((product) => (
                    <tr key={product.product_id}>
                      <td>{product.name}</td>
                      <td>{product.quantity}</td>
                      <td>{product.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="accessible__panel accessible__panel--placeholder">
          <h3>Executive sales (placeholder)</h3>
          <p>
            Empty module for Mariana Restrepo’s chain sales in USD and COP —
            wired later. Structure only.
          </p>
        </div>
      </div>
    </section>
  );
}
