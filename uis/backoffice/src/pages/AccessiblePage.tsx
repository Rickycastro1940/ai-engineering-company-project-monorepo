import { useEffect, useState } from "react";
import {
  fetchLocationsOverview,
  type LocationsOverview,
} from "../lib/api";
import "./AccessiblePage.css";

export function AccessiblePage() {
  const [overview, setOverview] = useState<LocationsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchLocationsOverview();
        if (!cancelled) {
          setOverview(data);
        }
      } catch (err) {
        if (!cancelled) {
          setOverview(null);
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load company locations",
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
        <p className="accessible__kicker">Welcome</p>
        <h2 id="accessible-title">Brasaland operations entry</h2>
        <p className="accessible__lead">
          Internal entry view for Brasaland Digital. This screen surfaces the
          company location footprint from <strong>CONTEXT.md</strong> via{" "}
          <code>GET /locations/overview</code> — 14 company-owned restaurants
          across Colombia and Florida, with COP and USD.
        </p>
      </div>

      <div className="accessible__dashboard" aria-label="Empty dashboard frame">
        <div className="accessible__panel accessible__panel--span">
          <h3>Company footprint</h3>
          {loading && <p className="accessible__status">Loading locations…</p>}
          {error && (
            <p className="accessible__error" role="alert">
              {error}. Start the API with{" "}
              <code>uvicorn api.app:app --reload</code> on port 8000.
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
            <p className="accessible__status">Waiting for API data…</p>
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
