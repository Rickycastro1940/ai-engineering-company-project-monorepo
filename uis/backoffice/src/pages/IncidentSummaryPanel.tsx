import { useCallback, useEffect, useState } from "react";
import { AsyncPanel } from "../components/AsyncState";
import { apiRequest, toUserFacingMessage } from "../lib/api";
import {
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  type IncidentSummary,
} from "../lib/incidents";

function MetricList({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ label: string; count: number }>;
}) {
  return (
    <section className="incident-metric">
      <h3>{title}</h3>
      <ul>
        {rows.map((row) => (
          <li key={row.label}>
            <span>{row.label}</span>
            <strong>{row.count}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function IncidentSummaryPanel({ reloadToken = 0 }: { reloadToken?: number }) {
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<IncidentSummary | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const body = await apiRequest<IncidentSummary>("/api/incidents/summary");
      setSummary(body);
      setStatus("success");
    } catch (requestError) {
      setSummary(null);
      setError(toUserFacingMessage(requestError, "Incident totals could not be loaded."));
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  return (
    <div className="incident-summary">
      <AsyncPanel
        status={status}
        loadingLabel="Loading incident totals…"
        error={error}
        onRetry={() => void load()}
      >
        {summary ? (
          <>
            <p className="incident-summary__total">
              <strong>{summary.total}</strong> incidents in the manager
            </p>
            <div className="incident-summary__grid">
              <MetricList
                title="By status"
                rows={INCIDENT_STATUSES.map((option) => ({
                  label: option.label,
                  count: summary.by_status[option.value] ?? 0,
                }))}
              />
              <MetricList
                title="By category"
                rows={INCIDENT_CATEGORIES.map((option) => ({
                  label: option.label,
                  count: summary.by_category[option.value] ?? 0,
                }))}
              />
              <MetricList
                title="By origin"
                rows={INCIDENT_ORIGINS.map((option) => ({
                  label: option.label,
                  count: summary.by_origin[option.value] ?? 0,
                }))}
              />
              <MetricList
                title="By branch"
                rows={INCIDENT_BRANCHES.map((option) => ({
                  label: option.label,
                  count: summary.by_branch[option.value] ?? 0,
                }))}
              />
            </div>
          </>
        ) : null}
      </AsyncPanel>
    </div>
  );
}

