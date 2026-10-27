export const RFP_TICKET_CREATED = "rfp_ticket_created";

type NamedFrame = {
  event: string;
  data: Record<string, unknown>;
};

/** A Brasaland restaurant on the 14-location roster. */
export type RfpRestaurant = {
  id: string;
  name: string;
  city: string;
  country: string;
  currency: string;
};

export type RfpTicket = {
  ticket_id: string;
  status: string;
  rfp_id: string;
  company: string;
  client_name: string;
  /** Client site as written on the request (Medellín, Florida, …). */
  location: string;
  /** Market of the Brasaland restaurants on this ticket. */
  country?: string;
  /** COP for Colombia, USD for Florida. Never converted. */
  currency?: string;
  /** Brasaland restaurants that would serve this request. One market only. */
  locations?: RfpRestaurant[];
  service_type: string;
  scope: string;
  deadline: string;
  budget_range: string | null;
  departments_needed: string[];
  raw_pdf_path: string;
  owner: string;
  created_at: string;
  updated_at: string;
  terminal: boolean;
  title?: string | null;
  event_id?: number;
};

/** Colombia (COP) and Florida (USD) cannot share one ticket. */
export function restaurantsShareOneMarket(
  sites: Array<{ country: string; currency: string }>,
): boolean {
  if (sites.length === 0) {
    return false;
  }
  const country = sites[0].country;
  const currency = sites[0].currency;
  return sites.every((site) => site.country === country && site.currency === currency);
}

export const RFP_DEPARTMENTS = [
  { id: "marketing", label: "Marketing — Camila Ospina" },
  { id: "operaciones", label: "Restaurant Operations — Felipe Guerrero" },
  { id: "procurement", label: "Procurement — Lucía Fernández" },
  { id: "training", label: "Training — Jake Morrison" },
] as const;

export function isRfpTicket(value: unknown): value is RfpTicket {
  if (!value || typeof value !== "object") {
    return false;
  }
  const row = value as RfpTicket;
  return typeof row.ticket_id === "string" && row.ticket_id.length > 0 && typeof row.status === "string";
}

/** Banner copy for a ticket that arrived on the stream. Distinct from location and inventory rows. */
export function rfpArrivalLabel(ticket: RfpTicket): string {
  const money = ticket.currency ? ` · ${ticket.currency}` : "";
  return `New RFP · ${ticket.status} · ${ticket.client_name} · ${ticket.location}${money}`;
}

export function latestEventId(tickets: RfpTicket[]): string | null {
  const max = tickets.reduce((cursor, ticket) => Math.max(cursor, ticket.event_id ?? 0), 0);
  return max > 0 ? String(max) : null;
}

/** One row per ticket_id. A replay and a live frame for the same id stay a single card. */
export function reduceRfpTickets(tickets: RfpTicket[], frame: NamedFrame): RfpTicket[] {
  if (frame.event !== RFP_TICKET_CREATED || !isRfpTicket(frame.data)) {
    return tickets;
  }
  const next = frame.data;
  return [next, ...tickets.filter((row) => row.ticket_id !== next.ticket_id)];
}

export function mergeRfpTickets(current: RfpTicket[], incoming: RfpTicket[]): RfpTicket[] {
  const byId = new Map<string, RfpTicket>();
  for (const row of current) {
    byId.set(row.ticket_id, row);
  }
  for (const row of incoming) {
    if (isRfpTicket(row)) {
      byId.set(row.ticket_id, row);
    }
  }
  return [...byId.values()].sort((left, right) => (left.created_at < right.created_at ? 1 : -1));
}
