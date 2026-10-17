import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, apiRequest, sanitizeFieldMessage, toUserFacingMessage } from "../lib/api";
import {
  INCIDENT_BRANCHES,
  INCIDENT_CATEGORIES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  validateIncidentDraft,
  type Incident,
  type IncidentDraft,
} from "../lib/incidents";
import "./Incidents.css";

const EMPTY: IncidentDraft = {
  title: "",
  description: "",
  category: "equipment_failure",
  status: "open",
  origin: "branch",
  branch: "medellin_centro",
};

function fieldErrorsFromApi(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== "object") {
    return {};
  }
  const raw = (error.details as { errors?: unknown }).errors;
  if (!Array.isArray(raw)) {
    return {};
  }
  const errors: Record<string, string> = {};
  for (const item of raw) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const field = "field" in item ? item.field : undefined;
    const message = "message" in item ? item.message : undefined;
    if (typeof field === "string" && typeof message === "string") {
      errors[field] = sanitizeFieldMessage(message);
    }
  }
  return errors;
}

export function IncidentFormPage() {
  const [draft, setDraft] = useState<IncidentDraft>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function update<K extends keyof IncidentDraft>(key: K, value: IncidentDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => {
      if (!current[key]) {
        return current;
      }
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setConfirmation("");
    const validation = validateIncidentDraft(draft);
    setFieldErrors(validation);
    if (Object.keys(validation).length > 0) {
      return;
    }
    setIsSubmitting(true);
    try {
      await apiRequest<Incident>("/api/incidents", {
        method: "POST",
        body: JSON.stringify({
          title: draft.title.trim(),
          description: draft.description.trim(),
          category: draft.category,
          status: draft.status,
          origin: draft.origin,
          branch: draft.branch,
        }),
      });
      setDraft(EMPTY);
      setFieldErrors({});
      setConfirmation("Incident logged. The operations team can see it in the incident list.");
    } catch (requestError) {
      const fields = fieldErrorsFromApi(requestError);
      setFieldErrors(fields);
      if (Object.keys(fields).length === 0) {
        setFormError(toUserFacingMessage(requestError, "The incident could not be saved. Try again."));
      } else {
        setFormError("Please correct the highlighted fields.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  const branchHighlighted = draft.origin === "branch";

  return (
    <section className="auth-card auth-card--embedded incident-form">
      <p className="auth-card__eyebrow">Restaurant operations</p>
      <h2>Log an incident</h2>
      <p className="auth-card__lead">
        Location managers and headquarters use this form so Felipe Guerrero can see what is
        happening without waiting for a weekly call. Branch names are the kitchen labels.
      </p>
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <label>
          Title
          <input
            value={draft.title}
            onChange={(event) => update("title", event.target.value)}
            maxLength={120}
            aria-invalid={Boolean(fieldErrors.title)}
            required
          />
          {fieldErrors.title ? <span className="auth-form__field-error">{fieldErrors.title}</span> : null}
        </label>
        <label>
          Description
          <textarea
            value={draft.description}
            onChange={(event) => update("description", event.target.value)}
            aria-invalid={Boolean(fieldErrors.description)}
            required
          />
          {fieldErrors.description ? (
            <span className="auth-form__field-error">{fieldErrors.description}</span>
          ) : null}
        </label>
        <label>
          Category
          <select
            value={draft.category}
            onChange={(event) => update("category", event.target.value)}
            aria-invalid={Boolean(fieldErrors.category)}
          >
            {INCIDENT_CATEGORIES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {fieldErrors.category ? <span className="auth-form__field-error">{fieldErrors.category}</span> : null}
        </label>
        <label>
          Status
          <select value={draft.status} onChange={(event) => update("status", event.target.value)}>
            {INCIDENT_STATUSES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Origin
          <select value={draft.origin} onChange={(event) => update("origin", event.target.value)}>
            {INCIDENT_ORIGINS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={branchHighlighted ? "incident-field--branch" : undefined}>
          Branch
          {branchHighlighted ? (
            <span className="incident-field__hint">You are reporting from a specific location.</span>
          ) : null}
          <select
            value={draft.branch}
            onChange={(event) => update("branch", event.target.value)}
            aria-invalid={Boolean(fieldErrors.branch)}
            required
          >
            {INCIDENT_BRANCHES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {fieldErrors.branch ? <span className="auth-form__field-error">{fieldErrors.branch}</span> : null}
        </label>
        {formError ? (
          <p className="auth-form__error" role="alert">
            {formError}
          </p>
        ) : null}
        {confirmation ? (
          <p className="auth-form__success" role="status">
            {confirmation}
          </p>
        ) : null}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? (
            <span className="async-state">
              <span className="async-state__spinner" aria-hidden="true" />
              Saving incident…
            </span>
          ) : (
            "Save incident"
          )}
        </button>
      </form>
      <p className="auth-card__muted">
        <Link to="/incidents">Back to the incident list</Link>
      </p>
    </section>
  );
}
