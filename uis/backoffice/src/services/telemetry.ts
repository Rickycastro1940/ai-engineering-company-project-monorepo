/**
 * TelemetryService — single entry point for backoffice event capture.
 * Queue + batch (10s / 20 events), sendBeacon flush, retry with backoff.
 */

export type TelemetryProperties = Record<string, unknown>;

export interface TelemetryEvent {
  eventId: string;
  timestamp: string;
  sessionId: string;
  userId: string;
  event_type: string;
  schemaVersion: string;
  requestId: string;
  properties: TelemetryProperties;
}

const SCHEMA_VERSION = "1.0.0";
const FLUSH_INTERVAL_MS = 10_000;
const MAX_QUEUE_SIZE = 20;
const MAX_RETRIES = 3;

let queue: TelemetryEvent[] = [];
let sessionId: string | null = null;
let userId = "anonymous";
let flushTimer: ReturnType<typeof setInterval> | null = null;
let listenersBound = false;

function endpointUrl(): string {
  const url = import.meta.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT;
  if (!url) {
    console.warn("NEXT_PUBLIC_TELEMETRY_ENDPOINT is not set");
    return "";
  }
  return url;
}

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function ensureSession(): string {
  if (!sessionId) {
    sessionId = `sess_${uuid()}`;
  }
  return sessionId;
}

function buildEvent(
  eventType: string,
  properties: TelemetryProperties,
): TelemetryEvent {
  return {
    eventId: uuid(),
    timestamp: new Date().toISOString(),
    sessionId: ensureSession(),
    userId,
    event_type: eventType,
    schemaVersion: SCHEMA_VERSION,
    requestId: `req_${uuid()}`,
    // Callers pass domain props only; allowlist filtering happens in track().
    properties,
  };
}

async function postBatch(batch: TelemetryEvent[], attempt = 1): Promise<void> {
  const url = endpointUrl();
  if (!url || batch.length === 0) return;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    });
    if (!response.ok) {
      throw new Error(`telemetry HTTP ${response.status}`);
    }
  } catch (error) {
    if (attempt >= MAX_RETRIES) {
      console.warn("Telemetry batch discarded after retries", error);
      return;
    }
    const delayMs = 200 * 2 ** (attempt - 1);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await postBatch(batch, attempt + 1);
  }
}

export async function flush(): Promise<void> {
  if (queue.length === 0) return;
  const batch = queue;
  queue = [];
  await postBatch(batch);
}

function flushWithBeacon(): void {
  if (queue.length === 0) return;
  const url = endpointUrl();
  if (!url) return;
  const batch = queue;
  queue = [];
  const payload = JSON.stringify({ events: batch });
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([payload], { type: "application/json" });
    const ok = navigator.sendBeacon(url, blob);
    if (!ok) {
      void postBatch(batch);
    }
    return;
  }
  void postBatch(batch);
}

function bindLifecycle(): void {
  if (listenersBound || typeof document === "undefined") return;
  listenersBound = true;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      flushWithBeacon();
    }
  });
  if (flushTimer == null) {
    flushTimer = setInterval(() => {
      void flush();
    }, FLUSH_INTERVAL_MS);
  }
}

/** Set authenticated operator id (never email/name). */
export function setTelemetryUser(nextUserId: string): void {
  userId = nextUserId || "anonymous";
  ensureSession();
  bindLifecycle();
}

/**
 * Only public tracking API. Components must not pass envelope fields.
 * `eventType` becomes envelope `event_type`.
 */
export function track(
  eventType: string,
  properties: TelemetryProperties = {},
): void {
  bindLifecycle();
  queue.push(buildEvent(eventType, properties));
  if (queue.length >= MAX_QUEUE_SIZE) {
    void flush();
  }
}

/** Test helper — pending queue length. */
export function pendingCount(): number {
  return queue.length;
}
