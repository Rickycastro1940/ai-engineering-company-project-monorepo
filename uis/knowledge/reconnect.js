/** Growing wait before the next WebSocket open. Attempt 0 waits 1s, then 2s, 4s, capped at 30s. */
export function reconnectDelayMs(attempt) {
  const step = Number.isFinite(attempt) && attempt > 0 ? Math.floor(attempt) : 0;
  return Math.min(1000 * 2 ** step, 30000);
}
