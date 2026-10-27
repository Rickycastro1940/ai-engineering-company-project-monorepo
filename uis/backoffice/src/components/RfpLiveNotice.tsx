import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest } from "../lib/api";
import {
  RFP_TICKET_CREATED,
  isRfpTicket,
  latestEventId,
  mergeRfpTickets,
  reduceRfpTickets,
  rfpArrivalLabel,
  type RfpTicket,
} from "../lib/rfpNotifications";
import { connectRfpStream, type StreamStatus } from "../lib/rfpStream";
import type { ParsedSse } from "../lib/noSalesAlerts";
import "./RfpLiveNotice.css";

type TicketList = {
  tickets: RfpTicket[];
  count: number;
};

const STATUS_LABEL: Record<StreamStatus, string> = {
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
};

/**
 * Operations dashboard notice for corporate RFPs.
 * Recovery is Last-Event-ID on the stream, plus a refetch of GET /rfp/tickets
 * when the connection drops. Location and inventory data are left alone.
 */
export function RfpLiveNotice() {
  const [tickets, setTickets] = useState<RfpTicket[]>([]);
  const [freshIds, setFreshIds] = useState<string[]>([]);
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [reconnectSeconds, setReconnectSeconds] = useState<number | null>(null);
  const known = useRef<Set<string>>(new Set());

  useEffect(() => {
    const controller = new AbortController();

    void (async () => {
      let cursor: string | null = null;
      try {
        const snapshot = await apiRequest<TicketList>("/rfp/tickets");
        const rows = Array.isArray(snapshot.tickets) ? snapshot.tickets : [];
        if (controller.signal.aborted) {
          return;
        }
        setTickets(rows);
        for (const row of rows) {
          known.current.add(row.ticket_id);
        }
        cursor = latestEventId(rows);
      } catch {
        /* Replay on the stream still fills the notice when the channel is up. */
      }
      if (controller.signal.aborted) {
        return;
      }
      await connectRfpStream(
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
        { initialEventId: cursor },
      );
    })();

    return () => {
      controller.abort();
    };
  }, []);

  function applyFrame(frame: ParsedSse) {
    if (frame.event !== RFP_TICKET_CREATED || !isRfpTicket(frame.data)) {
      return;
    }
    const ticket = frame.data;
    const unseen = !known.current.has(ticket.ticket_id);
    known.current.add(ticket.ticket_id);
    setTickets((current) => reduceRfpTickets(current, frame));
    if (unseen) {
      setFreshIds((ids) => [ticket.ticket_id, ...ids.filter((id) => id !== ticket.ticket_id)]);
    }
  }

  async function refetchTickets() {
    try {
      const snapshot = await apiRequest<TicketList>("/rfp/tickets");
      const rows = Array.isArray(snapshot.tickets) ? snapshot.tickets : [];
      setTickets((current) => mergeRfpTickets(current, rows));
      for (const row of rows) {
        if (!known.current.has(row.ticket_id)) {
          setFreshIds((ids) => [row.ticket_id, ...ids.filter((id) => id !== row.ticket_id)]);
        }
        known.current.add(row.ticket_id);
      }
    } catch {
      /* Last-Event-ID replay still delivers tickets missed during the gap. */
    }
  }

  const arrival = tickets.find((ticket) => freshIds.includes(ticket.ticket_id)) ?? null;
  const badge =
    status === "reconnecting" && reconnectSeconds
      ? `Reconnect ${reconnectSeconds}s`
      : STATUS_LABEL[status];

  return (
    <section className="rfp-notice" aria-label="Corporate RFP notifications" aria-live="polite">
      <div className="rfp-notice__head">
        <div>
          <p className="rfp-notice__kicker">Marketing · Camila Ospina</p>
          <h2>Corporate RFP</h2>
        </div>
        <p className="rfp-notice__stream" role="status">
          Stream <span className={`rfp-notice__badge rfp-notice__badge--${status}`}>{badge}</span>
        </p>
      </div>
      {arrival ? (
        <p className="rfp-notice__arrival" role="status">
          {rfpArrivalLabel(arrival)}
        </p>
      ) : (
        <p className="rfp-notice__quiet">No new RFP has arrived since this dashboard opened.</p>
      )}
      {tickets.length > 0 ? (
        <ul>
          {tickets.slice(0, 3).map((ticket) => (
            <li key={ticket.ticket_id}>
              <strong>{ticket.client_name}</strong>
              {freshIds.includes(ticket.ticket_id) ? <span className="rfp-notice__new">New</span> : null}
              <span className="rfp-notice__status">{ticket.status}</span>
              <span>
                {ticket.location}
                {ticket.currency ? ` · ${ticket.currency}` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="rfp-notice__link">
        <Link to="/rfp-intake">Open RFP registration</Link>
      </p>
    </section>
  );
}
