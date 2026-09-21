import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AsyncPanel } from "../components/AsyncState";
import { fetchLocationsOverview, toUserFacingMessage, type LocationsOverview } from "../lib/api";
import {
  fetchInventory,
  inventoryErrorMessage,
  type InventoryProduct,
} from "../lib/inventory";
import "./AccessiblePage.css";

function emptyOverview(): LocationsOverview {
  return {
    company: "Brasaland",
    total_locations: 0,
    countries: [],
    currencies: [],
    colombia_count: 0,
    florida_count: 0,
    source: "",
    locations: [],
  };
}

export function AccessiblePage() {
  const [overview, setOverview] = useState<LocationsOverview | null>(null);
  const [inventory, setInventory] = useState<InventoryProduct[] | null>(null);
  const [locationStatus, setLocationStatus] = useState<"loading" | "success" | "error">("loading");
  const [inventoryStatus, setInventoryStatus] = useState<"loading" | "success" | "error">("loading");
  const [locationError, setLocationError] = useState<string | null>(null);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [locationNonce, setLocationNonce] = useState(0);
  const [inventoryNonce, setInventoryNonce] = useState(0);

  const retryLocations = useCallback(() => {
    setLocationNonce((value) => value + 1);
  }, []);

  const retryInventory = useCallback(() => {
    setInventoryNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setLocationStatus("loading");
    setLocationError(null);

    void (async () => {
      try {
        const locationData = await fetchLocationsOverview();
        if (cancelled) {
          return;
        }
        setOverview({
          company: locationData?.company ?? "Brasaland",
          total_locations: locationData?.total_locations ?? 0,
          countries: locationData?.countries ?? [],
          currencies: locationData?.currencies ?? [],
          colombia_count: locationData?.colombia_count ?? 0,
          florida_count: locationData?.florida_count ?? 0,
          source: locationData?.source ?? "",
          locations: locationData?.locations ?? [],
        });
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setOverview(null);
          setLocationError(
            toUserFacingMessage(err, "Location data could not be loaded. Try again in a moment."),
          );
        }
      } finally {
        if (!cancelled) {
          setLocationStatus(outcome);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [locationNonce]);

  useEffect(() => {
    let cancelled = false;
    let outcome: "success" | "error" = "error";
    setInventoryStatus("loading");
    setInventoryError(null);

    void (async () => {
      try {
        const inventoryData = await fetchInventory();
        if (cancelled) {
          return;
        }
        setInventory(Array.isArray(inventoryData) ? inventoryData : []);
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setInventory(null);
          setInventoryError(
            inventoryErrorMessage(
              err,
              "Current kitchen stock could not be loaded. Try again in a moment.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setInventoryStatus(outcome);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [inventoryNonce]);

  const footprint = overview ?? emptyOverview();
  const roster = footprint.locations ?? [];
  const currencies = footprint.currencies ?? [];
  const stock = inventory ?? [];

  return (
    <section className="accessible" aria-labelledby="accessible-title">
      <div className="accessible__welcome">
        <p className="accessible__kicker">Restaurant Operations · Felipe Guerrero</p>
        <h2 id="accessible-title">Brasaland operations entry</h2>
        <p className="accessible__lead">
          Restaurant Operations for Felipe Guerrero and Executive Direction for
          Mariana Restrepo. After login, this page loads the 14 company-owned
          restaurants across Colombia and Florida (COP and USD) plus current
          kitchen stock — so headquarters is not waiting on WhatsApp ingredient
          orders.
        </p>
      </div>

      <div className="accessible__dashboard" aria-label="Authenticated operations dashboard">
        <div className="accessible__panel accessible__panel--span">
          <h3>Company footprint</h3>
          <AsyncPanel
            status={locationStatus}
            loadingLabel="Loading protected location data…"
            error={locationError}
            onRetry={retryLocations}
            skeletonRows={3}
          >
            <dl className="accessible__stats">
              <div>
                <dt>Total locations</dt>
                <dd>{footprint.total_locations ?? 0}</dd>
              </div>
              <div>
                <dt>Colombia</dt>
                <dd>{footprint.colombia_count ?? 0}</dd>
              </div>
              <div>
                <dt>Florida (US)</dt>
                <dd>{footprint.florida_count ?? 0}</dd>
              </div>
              <div>
                <dt>Currencies</dt>
                <dd className="accessible__currencies">
                  {currencies.length === 0
                    ? "—"
                    : currencies.map((currency) => (
                        <span
                          key={currency}
                          className={
                            currency === "COP" ? "badge badge--cop" : "badge badge--usd"
                          }
                        >
                          {currency}
                        </span>
                      ))}
                </dd>
              </div>
            </dl>
            {footprint.source ? <p className="accessible__source">{footprint.source}</p> : null}
          </AsyncPanel>
        </div>

        <div className="accessible__panel">
          <h3>Location roster</h3>
          <AsyncPanel
            status={locationStatus}
            loadingLabel="Loading location roster…"
            error={locationError}
            onRetry={retryLocations}
            skeletonRows={6}
          >
            {roster.length === 0 ? (
              <p className="accessible__status">No locations were returned.</p>
            ) : (
              <ul className="accessible__list">
                {roster.map((location, index) => (
                  <li key={location?.id ?? `${location?.name ?? "location"}-${index}`}>
                    <span className="accessible__loc-name">{location?.name ?? "Unnamed location"}</span>
                    <span className="accessible__loc-meta">
                      {location?.city ?? "Unknown city"} · {location?.region ?? "Unknown region"} ·{" "}
                      <span
                        className={
                          location?.currency === "COP" ? "badge badge--cop" : "badge badge--usd"
                        }
                      >
                        {location?.currency ?? "—"}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </AsyncPanel>
        </div>

        <div className="accessible__panel">
          <h3>Kitchen stock</h3>
          <p className="accessible__link-row">
            <Link to="/inventory">Manage kitchen stock</Link>
            {" · "}
            <Link to="/inventory/products">Ingredients</Link>
            {" · "}
            <Link to="/inventory/orders">Ingredient orders</Link> to review current
            stock, stockouts, and supplier deliveries vs kitchen usage.
          </p>
          <AsyncPanel
            status={inventoryStatus}
            loadingLabel="Loading kitchen stock…"
            error={inventoryError}
            onRetry={retryInventory}
            skeletonRows={5}
          >
            {stock.length === 0 ? (
              <p className="accessible__status">No ingredients on hand yet.</p>
            ) : (
              <div className="accessible__table-wrap">
                <table className="accessible__table">
                  <thead>
                    <tr>
                      <th scope="col">Ingredient</th>
                      <th scope="col">Current stock</th>
                      <th scope="col">Unit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stock.map((product, index) => (
                      <tr key={product?.product_id ?? `${product?.name ?? "item"}-${index}`}>
                        <td>{product?.name ?? "Unnamed ingredient"}</td>
                        <td>{product?.quantity ?? "—"}</td>
                        <td>{product?.unit ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </AsyncPanel>
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
