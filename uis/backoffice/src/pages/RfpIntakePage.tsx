import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiRequest, toUserFacingMessage } from "../lib/api";
import {
  RFP_DEPARTMENTS,
  RFP_TICKET_CREATED,
  isRfpTicket,
  mergeRfpTickets,
  reduceRfpTickets,
  type RfpTicket,
} from "../lib/rfpNotifications";
import { connectRfpStream, type StreamStatus } from "../lib/rfpStream";
import type { ParsedSse } from "../lib/noSalesAlerts";
import "./RfpIntakePage.css";

type TicketList = {
  tickets: RfpTicket[];
  count: number;
};

const STATUS_LABEL: Record<StreamStatus, string> = {
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
};

export function RfpIntakePage() {
  const [tickets, setTickets] = useState<RfpTicket[]>([]);
  const [freshIds, setFreshIds] = useState<string[]>([]);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [reconnectSeconds, setReconnectSeconds] = useState<number | null>(null);
  const [clientName, setClientName] = useState("");
  const [location, setLocation] = useState("");
  const [serviceType, setServiceType] = useState("");
  const [scope, setScope] = useState("");
  const [deadline, setDeadline] = useState("");
  const [budgetRange, setBudgetRange] = useState("");
  const [title, setTitle] = useState("");
  const [departments, setDepartments] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const primed = useRef(false);
  const known = useRef<Set<string>>(new Set());

  useEffect(() => {
    const controller = new AbortController();
    void connectRfpStream(
      {
        onStatus: (next, delayMs) => {
          setStatus(next);
          setReconnectSeconds(delayMs == null ? null : Math.round(delayMs / 1000));
          if (next === "reconnecting") {
            void refetchTickets();
          }
        },
        onEvent: (frame) => {
          applyFrame(frame);
        },
      },
      controller.signal,
    );
    return () => {
      controller.abort();
    };
  }, []);

  useEffect(() => {
    void refetchTickets();
  }, []);

  function applyFrame(frame: ParsedSse) {
    if (frame.event !== RFP_TICKET_CREATED) {
      return;
    }
    setTickets((current) => {
      const next = reduceRfpTickets(current, frame);
      const ticket = isRfpTicket(frame.data) ? frame.data : null;
      if (ticket && primed.current && !known.current.has(ticket.ticket_id)) {
        setFreshIds((ids) => [ticket.ticket_id, ...ids.filter((id) => id !== ticket.ticket_id)]);
      }
      if (ticket) {
        known.current.add(ticket.ticket_id);
      }
      return next;
    });
    if (!primed.current) {
      window.setTimeout(() => {
        primed.current = true;
      }, 400);
    }
  }

  async function refetchTickets() {
    try {
      const snapshot = await apiRequest<TicketList>("/rfp/tickets");
      const rows = Array.isArray(snapshot.tickets) ? snapshot.tickets : [];
      setTickets((current) => mergeRfpTickets(current, rows));
      for (const row of rows) {
        known.current.add(row.ticket_id);
      }
    } catch {
      /* The stream replay still fills the list when the channel is up. */
    }
  }

  function toggleDepartment(id: string) {
    setDepartments((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!file) {
      setFormError("Choose the RFP file to register.");
      return;
    }
    const budget = budgetRange.trim();
    if (budget && !/COP|USD/i.test(budget)) {
      setFormError("Write the budget in COP or USD. Leave the amount as written.");
      return;
    }
    const body = new FormData();
    body.set("client_name", clientName.trim());
    body.set("location", location.trim());
    body.set("service_type", serviceType.trim());
    body.set("scope", scope.trim());
    body.set("deadline", deadline.trim());
    if (budget) {
      body.set("budget_range", budget);
    }
    if (title.trim()) {
      body.set("title", title.trim());
    }
    if (departments.length) {
      body.set("departments_needed", departments.join(","));
    }
    body.set("file", file);
    setSubmitting(true);
    try {
      const created = await apiRequest<RfpTicket>("/rfp/tickets", { method: "POST", body });
      setTickets((current) => mergeRfpTickets(current, [created]));
      if (!known.current.has(created.ticket_id)) {
        setFreshIds((ids) => [created.ticket_id, ...ids]);
      }
      known.current.add(created.ticket_id);
      setClientName("");
      setLocation("");
      setServiceType("");
      setScope("");
      setDeadline("");
      setBudgetRange("");
      setTitle("");
      setDepartments([]);
      setFile(null);
      setFileKey((value) => value + 1);
    } catch (error: unknown) {
      setFormError(toUserFacingMessage(error, "The RFP could not be registered. Check the fields and try again."));
    } finally {
      setSubmitting(false);
    }
  }

  const badge =
    status === "reconnecting" && reconnectSeconds
      ? `Reconnect ${reconnectSeconds}s`
      : STATUS_LABEL[status];

  return (
    <section className="rfp">
      <header className="rfp__intro">
        <p className="rfp__kicker">Marketing · Camila Ospina</p>
        <h2>Register a corporate RFP</h2>
        <p className="rfp__lead">
          Catering, concession, and co-branding requests open a ticket owned by Camila Ospina.
          The server sets the status to <strong>analyzing</strong>. Staff who are signed in see
          the ticket on this page without a reload. Amounts stay in COP or USD as written.
        </p>
        <p className="rfp__stream" role="status">
          Stream <span className={`rfp__badge rfp__badge--${status}`}>{badge}</span>
        </p>
      </header>

      <form className="rfp__form" onSubmit={onSubmit}>
        <h3>RFP fields</h3>
        <label>
          Client name
          <input value={clientName} onChange={(event) => setClientName(event.target.value)} required minLength={2} name="client_name" />
        </label>
        <label>
          Location
          <input value={location} onChange={(event) => setLocation(event.target.value)} required name="location" placeholder="Medellín or Florida" />
        </label>
        <label>
          Service type
          <input value={serviceType} onChange={(event) => setServiceType(event.target.value)} required name="service_type" placeholder="weekly catering, concession, co-branding" />
        </label>
        <label>
          Scope
          <textarea value={scope} onChange={(event) => setScope(event.target.value)} required name="scope" rows={3} placeholder="Diners, sites, and contract length" />
        </label>
        <label>
          Deadline
          <input value={deadline} onChange={(event) => setDeadline(event.target.value)} required name="deadline" placeholder="2026-11-30" />
        </label>
        <label>
          Budget range (optional)
          <input value={budgetRange} onChange={(event) => setBudgetRange(event.target.value)} name="budget_range" placeholder="48000000 COP/year or 60000-75000 USD/year" />
        </label>
        <label>
          Title (optional)
          <input value={title} onChange={(event) => setTitle(event.target.value)} name="title" />
        </label>
        <fieldset>
          <legend>Departments needed</legend>
          <p className="rfp__hint">Leave this empty when the classifier has not run yet. Use only the four Brasaland ids.</p>
          {RFP_DEPARTMENTS.map((department) => (
            <label key={department.id} className="rfp__check">
              <input
                type="checkbox"
                checked={departments.includes(department.id)}
                onChange={() => toggleDepartment(department.id)}
              />
              <span>
                <code>{department.id}</code> — {department.label}
              </span>
            </label>
          ))}
        </fieldset>
        <label>
          RFP file
          <input
            key={fileKey}
            type="file"
            name="file"
            accept=".pdf,.doc,.docx,.txt,.md,.html,.htm"
            required
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        {formError ? (
          <p className="rfp__error" role="alert">
            {formError}
          </p>
        ) : null}
        <button type="submit" disabled={submitting}>
          {submitting ? "Registering…" : "Register RFP"}
        </button>
      </form>

      <div className="rfp__list" aria-live="polite">
        <h3>Live tickets</h3>
        {tickets.length === 0 ? (
          <p className="rfp__empty">No RFP has been registered in this session yet.</p>
        ) : (
          <ul>
            {tickets.map((ticket) => (
              <li key={ticket.ticket_id}>
                <div className="rfp__row">
                  <strong>{ticket.client_name}</strong>
                  {freshIds.includes(ticket.ticket_id) ? <span className="rfp__new">New</span> : null}
                  <span className="rfp__status">{ticket.status}</span>
                </div>
                <p>
                  {ticket.service_type} · {ticket.location}
                </p>
                <p>{ticket.scope}</p>
                <p>
                  Deadline {ticket.deadline}
                  {ticket.budget_range ? ` · ${ticket.budget_range}` : ""}
                </p>
                <p>
                  Owner {ticket.owner}
                  {ticket.departments_needed.length
                    ? ` · ${ticket.departments_needed.join(", ")}`
                    : ""}
                </p>
                <p className="rfp__meta">
                  {ticket.ticket_id} · {ticket.company}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
