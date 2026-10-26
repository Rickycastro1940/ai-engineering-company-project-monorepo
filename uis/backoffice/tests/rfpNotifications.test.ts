import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { consumeSseBuffer, reconnectDelayMs } from "../src/lib/noSalesAlerts.ts";
import {
  latestEventId,
  mergeRfpTickets,
  reduceRfpTickets,
  restaurantsShareOneMarket,
  rfpArrivalLabel,
  type RfpTicket,
} from "../src/lib/rfpNotifications.ts";

const andes: RfpTicket = {
  ticket_id: "abc",
  status: "analyzing",
  rfp_id: "rfp_abc",
  company: "brasaland",
  client_name: "Andes Tech Solutions",
  location: "Medellín",
  country: "Colombia",
  currency: "COP",
  locations: [
    {
      id: "co-med-centro",
      name: "Medellín Centro",
      city: "Medellín",
      country: "Colombia",
      currency: "COP",
    },
    {
      id: "co-med-elpoblado",
      name: "Medellín El Poblado",
      city: "Medellín",
      country: "Colombia",
      currency: "COP",
    },
  ],
  service_type: "weekly catering",
  scope: "220 employees",
  deadline: "2026-11-30",
  budget_range: "48000000 COP/year",
  departments_needed: ["marketing", "operaciones", "procurement"],
  raw_pdf_path: "data/uploads/rfp/abc/andes.pdf",
  owner: "Camila Ospina",
  event_id: 4,
  created_at: "2026-10-26T16:00:00Z",
  updated_at: "2026-10-26T16:00:00Z",
  terminal: false,
};

const sunset: RfpTicket = {
  ...andes,
  ticket_id: "def",
  rfp_id: "rfp_def",
  client_name: "Sunset Bay Resorts",
  location: "Florida",
  country: "United States",
  currency: "USD",
  locations: [
    {
      id: "us-mia-brickell",
      name: "Miami Brickell",
      city: "Miami",
      country: "United States",
      currency: "USD",
    },
    {
      id: "us-mia-downtown",
      name: "Miami Downtown",
      city: "Miami",
      country: "United States",
      currency: "USD",
    },
  ],
  service_type: "co-branded concession",
  budget_range: "60000-75000 USD/year",
  departments_needed: ["marketing", "operaciones", "procurement", "training"],
  event_id: 5,
  created_at: "2026-10-26T16:05:00Z",
};

describe("RFP registration notifications", () => {
  it("keeps one card when the same analyzing ticket is replayed", () => {
    const frame = {
      id: "1",
      event: "rfp_ticket_created",
      data: andes as unknown as Record<string, unknown>,
    };
    const once = reduceRfpTickets([], frame);
    const twice = reduceRfpTickets(once, frame);
    assert.equal(twice.length, 1);
    assert.equal(twice[0].status, "analyzing");
    assert.equal(twice[0].budget_range, "48000000 COP/year");
  });

  it("ignores unnamed events and merges a snapshot without duplicating ids", () => {
    const withLive = reduceRfpTickets([andes], {
      id: "2",
      event: "rfp_ticket_created",
      data: sunset as unknown as Record<string, unknown>,
    });
    const ignored = reduceRfpTickets(withLive, {
      id: null,
      event: "message",
      data: { ticket_id: "other", status: "analyzing" },
    });
    const merged = mergeRfpTickets(ignored, [andes, sunset]);
    assert.deepEqual(
      merged.map((row) => row.ticket_id),
      ["def", "abc"],
    );
    assert.equal(merged.length, 2);
    assert.equal(merged[0].currency, "USD");
    assert.equal(merged[1].currency, "COP");
    assert.deepEqual(
      merged[0].locations?.map((site) => site.id),
      ["us-mia-brickell", "us-mia-downtown"],
    );
    assert.ok(restaurantsShareOneMarket(andes.locations ?? []));
    assert.ok(restaurantsShareOneMarket(sunset.locations ?? []));
    assert.equal(
      restaurantsShareOneMarket([...(andes.locations ?? []), ...(sunset.locations ?? [])]),
      false,
    );
  });

  it("parses a named analyzing frame and backs off 1s, 2s, then 4s", () => {
    const raw = [
      "id: 4",
      "event: rfp_ticket_created",
      `data: ${JSON.stringify(andes)}`,
      "",
      "",
    ].join("\n");
    const parsed = consumeSseBuffer(raw);
    assert.equal(parsed.events.length, 1);
    assert.equal(parsed.events[0].event, "rfp_ticket_created");
    assert.equal(parsed.events[0].data.status, "analyzing");
    assert.equal(reconnectDelayMs(1), 1000);
    assert.equal(reconnectDelayMs(2), 2000);
    assert.equal(reconnectDelayMs(3), 4000);
  });

  it("labels a new analyzing ticket apart from the roster and resumes after its event id", () => {
    const label = rfpArrivalLabel(andes);
    assert.match(label, /New RFP/);
    assert.match(label, /analyzing/);
    assert.match(label, /Andes Tech Solutions/);
    assert.match(label, /COP/);
    assert.equal(label.includes("inventory"), false);
    assert.equal(latestEventId([andes, sunset]), "5");
    const replayed = reduceRfpTickets([andes], {
      id: "4",
      event: "rfp_ticket_created",
      data: andes as unknown as Record<string, unknown>,
    });
    assert.equal(replayed.length, 1);
  });
});
