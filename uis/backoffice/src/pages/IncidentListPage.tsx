import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AsyncPanel } from "../components/AsyncState";
import { apiRequest, toUserFacingMessage } from "../lib/api";
import {
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  STATUS_TRANSITIONS,
  labelFor,
  type Incident,
} from "../lib/incidents";
import { IncidentSummaryPanel } from "./IncidentSummaryPanel";
import "./Incidents.css";

type Filters = {
  status: string;
  origin: string;
  branch: string;
};

const EMPTY_FILTERS: Filters = { status: "", origin: "", branch: "" };

function queryFor(filters: Filters): string {
  const params = new URLSearchParams();
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.origin) {
    params.set("origin", filters.origin);
  }
  if (filters.branch) {
    params.set("branch", filters.branch);
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export function IncidentListPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [rowNotice, setRowNotice] = useState("");
  const [summaryToken, setSummaryToken] = useState(0);

  const load = useCallback(async (nextFilters: Filters) => {
    setStatus("loading");
    setError(null);
    setRowNotice("");
    try {
      const rows = await apiRequest<Incident[]>(`/api/incidents${queryFor(nextFilters)}`);
      setIncidents(rows);
      setStatus("success");
    } catch (requestError) {
      setIncidents([]);
      setError(toUserFacingMessage(requestError, "Incidents could not be loaded."));
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load(filters);
  }, [filters, load]);

  async function changeStatus(incident: Incident, nextStatus: string) {
    if (nextStatus === incident.status) {
      return;
    }
    const previous = incidents;
    setRowNotice("");
    setSavingId(incident.id);
    setIncidents((current) =>
      current.map((row) => (row.id === incident.id ? { ...row, status: nextStatus } : row)),
    );
    try {
      const updated = await apiRequest<Incident>(`/api/incidents/${incident.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      setIncidents((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setSummaryToken((current) => current + 1);
    } catch (requestError) {
      setIncidents(previous);
      setRowNotice(toUserFacingMessage(requestError, "The status could not be updated. It was left unchanged."));
    } finally {
      setSavingId(null);
    }
  }

  const filtersActive = Boolean(filters.status || filters.origin || filters.branch);

  return (
    <div className="incident-page">
      <header className="incident-page__header">
        <div>
          <p className="auth-card__eyebrow">Restaurant operations</p>
          <h2>Incidents</h2>
          <p className="auth-card__lead">
            Every logged report across Colombia and Florida. Open customer complaints older than 48
            hours stay visible here by status, category, and the time they were logged.
          </p>
        </div>
        <Link className="incident-page__action" to="/incidents/new">
          Log an incident
        </Link>
      </header>

      <form
        className="incident-filters"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <label>
          Status
          <select
            value={filters.status}
            onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}
          >
            <option value="">All statuses</option>
            {INCIDENT_STATUSES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Origin
          <select
            value={filters.origin}
            onChange={(event) => setFilters((current) => ({ ...current, origin: event.target.value }))}
          >
            <option value="">All origins</option>
            {INCIDENT_ORIGINS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Branch
          <select
            value={filters.branch}
            onChange={(event) => setFilters((current) => ({ ...current, branch: event.target.value }))}
          >
            <option value="">All branches</option>
            {INCIDENT_BRANCHES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </form>

      {rowNotice ? (
        <p className="auth-form__error" role="alert">
          {rowNotice}
        </p>
      ) : null}

      <AsyncPanel status={status} loadingLabel="Loading incidents…" error={error} onRetry={() => void load(filters)}>
        {incidents.length === 0 ? (
          <p className="incident-empty" role="status">
            {filtersActive
              ? "No incidents match these filters. Clear a filter or log a new incident."
              : "No incidents have been logged yet. Use Log an incident to add the first one."}
          </p>
        ) : (
          <div className="incident-table-wrap">
            <table className="incident-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Branch</th>
                  <th>Category</th>
                  <th>Origin</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((incident) => {
                  const nextStatuses = STATUS_TRANSITIONS[incident.status] ?? [];
                  return (
                    <tr key={incident.id}>
                      <td>
                        <strong>{incident.title}</strong>
                        <span className="incident-table__meta">{incident.created_at.slice(0, 10)}</span>
                      </td>
                      <td>{labelFor(INCIDENT_BRANCHES, incident.branch)}</td>
                      <td>{labelFor(INCIDENT_CATEGORIES, incident.category)}</td>
                      <td>{labelFor(INCIDENT_ORIGINS, incident.origin)}</td>
                      <td>
                        <select
                          aria-label={`Status for ${incident.title}`}
                          value={incident.status}
                          disabled={savingId === incident.id || nextStatuses.length === 0}
                          onChange={(event) => void changeStatus(incident, event.target.value)}
                        >
                          <option value={incident.status}>{labelFor(INCIDENT_STATUSES, incident.status)}</option>
                          {nextStatuses.map((value) => (
                            <option key={value} value={value}>
                              {labelFor(INCIDENT_STATUSES, value)}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </AsyncPanel>

      <section className="incident-page__summary" aria-label="Incident totals">
        <h2>Totals</h2>
        <IncidentSummaryPanel reloadToken={summaryToken} />
      </section>
    </div>
  );
}

export function IncidentSummaryPage() {
  return (
    <section className="incident-page">
      <header className="incident-page__header">
        <div>
          <p className="auth-card__eyebrow">Executive</p>
          <h2>Incident summary</h2>
          <p className="auth-card__lead">
            Open, in progress, resolved, and discarded incidents by category, origin, and branch.
          </p>
        </div>
        <Link className="incident-page__action" to="/incidents">
          Incident list
        </Link>
      </header>
      <IncidentSummaryPanel />
    </section>
  );
}
