import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { consumeSseBuffer, reconnectDelayMs } from "../src/lib/noSalesAlerts.ts";
import {
  mergeRfpTickets,
  reduceRfpTickets,
  type RfpTicket,
} from "../src/lib/rfpNotifications.ts";

const andes: RfpTicket = {
  ticket_id: "abc",
  status: "analyzing",
  rfp_id: "rfp_abc",
  company: "brasaland",
  client_name: "Andes Tech Solutions",
  location: "Medellín",
  service_type: "weekly catering",
  scope: "220 employees",
  deadline: "2026-11-30",
  budget_range: "48000000 COP/year",
  departments_needed: ["marketing", "operaciones", "procurement"],
  raw_pdf_path: "data/uploads/rfp/abc/andes.pdf",
  owner: "Camila Ospina",
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
  service_type: "co-branded concession",
  budget_range: "60000-75000 USD/year",
  departments_needed: ["marketing", "operaciones", "procurement", "training"],
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
});
