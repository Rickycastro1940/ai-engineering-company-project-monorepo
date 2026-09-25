import { useCallback, useEffect, useMemo, useState } from "react";
import { AsyncPanel } from "../components/AsyncState";
import {
  fetchLatestPipelineRun,
  fetchWeeklyLocationPerformance,
  toUserFacingMessage,
  type PipelineRunLatest,
  type WeeklyLocationPerformanceRow,
} from "../lib/api";
import "./WeeklyPerformancePage.css";

const LOCATION_LABELS: Record<string, string> = {
  "co-med-centro": "Medellín Centro",
  "co-med-elpoblado": "Medellín El Poblado",
  "co-bog-chapinero": "Bogotá Chapinero",
  "co-bog-norte": "Bogotá Norte",
  "co-cali-norte": "Cali Norte",
  "co-barranquilla": "Barranquilla",
  "co-cartagena": "Cartagena",
  "co-pereira": "Pereira",
  "us-mia-brickell": "Miami Brickell",
  "us-mia-downtown": "Miami Downtown",
  "us-orlando": "Orlando",
  "us-tampa": "Tampa",
  "us-ftlauderdale": "Fort Lauderdale",
  "us-jacksonville": "Jacksonville",
};

function formatMoney(value: number, currency: string): string {
  const amount = Number.isFinite(value) ? value : 0;
  if (currency === "COP") {
    return new Intl.NumberFormat("es-CO", {
      style: "currency",
      currency: "COP",
      maximumFractionDigits: 0,
    }).format(amount);
  }
  if (currency === "USD") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  }
  return String(amount);
}

function formatRatio(value: number): string {
  const ratio = Number.isFinite(value) ? value : 0;
  return `${(ratio * 100).toFixed(2)}%`;
}

function locationLabel(locationId: string): string {
  return LOCATION_LABELS[locationId] ?? locationId;
}

/** Chain week is [Monday, next Monday) in America/Bogota. */
function chainWeekWindowLabel(weekStart: string | null): string {
  if (!weekStart) {
    return "—";
  }
  const start = new Date(`${weekStart}T00:00:00`);
  if (Number.isNaN(start.getTime())) {
    return weekStart;
  }
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  const endIso = end.toISOString().slice(0, 10);
  return `${weekStart} → ${endIso} (exclusive) · America/Bogota`;
}

export function WeeklyPerformancePage() {
  const [weekStart, setWeekStart] = useState<string | null>(null);
  const [rows, setRows] = useState<WeeklyLocationPerformanceRow[]>([]);
  const [runMeta, setRunMeta] = useState<PipelineRunLatest | null>(null);
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
        const [kpiPayload, latestRun] = await Promise.all([
          fetchWeeklyLocationPerformance(),
          fetchLatestPipelineRun().catch(() => null),
        ]);
        if (cancelled) {
          return;
        }
        setWeekStart(kpiPayload?.week_start ?? null);
        setRows(Array.isArray(kpiPayload?.locations) ? kpiPayload.locations : []);
        setRunMeta(latestRun);
        outcome = "success";
      } catch (err: unknown) {
        if (!cancelled) {
          setRows([]);
          setWeekStart(null);
          setRunMeta(null);
          setError(
            toUserFacingMessage(
              err,
              "Weekly location performance could not be loaded. Try again in a moment.",
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

  const colombia = useMemo(
    () => rows.filter((row) => row.country === "Colombia"),
    [rows],
  );
  const florida = useMemo(
    () => rows.filter((row) => row.country === "United States"),
    [rows],
  );
  const stockoutTotal = useMemo(
    () => rows.reduce((sum, row) => sum + (row.stockout_events_count || 0), 0),
    [rows],
  );
  const priceAlertTotal = useMemo(
    () => rows.reduce((sum, row) => sum + (row.price_alert_events_count || 0), 0),
    [rows],
  );

  return (
    <section className="wlp" aria-labelledby="wlp-title">
      <div className="wlp__welcome">
        <p className="wlp__kicker">Monday weekly report · America/Bogota</p>
        <h2 id="wlp-title">Weekly location cost &amp; waste</h2>
        <p className="wlp__lead">
          For Mariana Restrepo, Felipe Guerrero, and Lucía Fernández. Reads{" "}
          <code>GET /reporting/weekly-location-performance</code> — Purchase cost,
          Waste cost, Waste ratio, Stockout frequency, and Price alert frequency per
          location, in COP or USD. Does not use engineering telemetry.
        </p>
      </div>

      <div className="wlp__dashboard" aria-label="Weekly location performance dashboard">
        <div className="wlp__panel wlp__panel--span">
          <h3>Chain week period</h3>
          <AsyncPanel
            status={status}
            loadingLabel="Loading weekly KPIs…"
            error={error}
            onRetry={retry}
            skeletonRows={2}
          >
            <dl className="wlp__stats">
              <div>
                <dt>Week start (Monday)</dt>
                <dd>{weekStart ?? "—"}</dd>
              </div>
              <div className="wlp__stats-span">
                <dt>Period covered</dt>
                <dd className="wlp__period">{chainWeekWindowLabel(weekStart)}</dd>
              </div>
              <div>
                <dt>Locations with data</dt>
                <dd>{rows.length}</dd>
              </div>
              <div>
                <dt>Colombia rows (COP)</dt>
                <dd>{colombia.length}</dd>
              </div>
              <div>
                <dt>Florida rows (USD)</dt>
                <dd>{florida.length}</dd>
              </div>
              <div>
                <dt>Stockout frequency (total)</dt>
                <dd>{stockoutTotal}</dd>
              </div>
              <div>
                <dt>Price alert frequency (total)</dt>
                <dd>{priceAlertTotal}</dd>
              </div>
            </dl>
            {runMeta?.status ? (
              <p className="wlp__run">
                Last pipeline run: <strong>{runMeta.status}</strong>
                {runMeta.window_start && runMeta.window_end
                  ? ` · window [${runMeta.window_start}, ${runMeta.window_end})`
                  : null}
                {typeof runMeta.records_processed === "number"
                  ? ` · ${runMeta.records_processed} events processed`
                  : null}
              </p>
            ) : null}
          </AsyncPanel>
        </div>

        <div className="wlp__panel wlp__panel--span">
          <h3>Location-week KPIs</h3>
          <AsyncPanel
            status={status}
            loadingLabel="Loading location KPI table…"
            error={error}
            onRetry={retry}
            skeletonRows={6}
          >
            {rows.length === 0 ? (
              <p className="wlp__empty">
                No rows in <code>reporting.weekly_location_performance</code> yet.
                Run{" "}
                <code>python data/pipelines/pipeline.py</code> for the previous
                chain week, then refresh.
              </p>
            ) : (
              <div className="wlp__table-wrap">
                <table className="wlp__table">
                  <thead>
                    <tr>
                      <th scope="col">Location</th>
                      <th scope="col">Country</th>
                      <th scope="col">Currency</th>
                      <th scope="col">Purchase cost</th>
                      <th scope="col">Waste cost</th>
                      <th scope="col">Waste ratio</th>
                      <th scope="col">Stockout frequency</th>
                      <th scope="col">Price alert frequency</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.location_id}>
                        <td>
                          <span className="wlp__loc-name">
                            {locationLabel(row.location_id)}
                          </span>
                          <span className="wlp__loc-id">{row.location_id}</span>
                        </td>
                        <td>{row.country}</td>
                        <td>
                          <span
                            className={
                              row.currency === "COP" ? "badge badge--cop" : "badge badge--usd"
                            }
                          >
                            {row.currency}
                          </span>
                        </td>
                        <td>{formatMoney(row.total_purchase_cost, row.currency)}</td>
                        <td>{formatMoney(row.total_waste_cost, row.currency)}</td>
                        <td>{formatRatio(row.waste_ratio)}</td>
                        <td>{row.stockout_events_count}</td>
                        <td>{row.price_alert_events_count}</td>
                      </tr>
                    ))}
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
