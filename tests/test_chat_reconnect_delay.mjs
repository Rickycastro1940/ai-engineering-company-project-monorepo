import assert from "node:assert/strict";
import test from "node:test";

import { reconnectDelayMs } from "../uis/knowledge/reconnect.js";

test("reconnect delay grows from 1s and caps at 30s", () => {
  assert.equal(reconnectDelayMs(0), 1000);
  assert.equal(reconnectDelayMs(1), 2000);
  assert.equal(reconnectDelayMs(2), 4000);
  assert.equal(reconnectDelayMs(4), 16000);
  assert.equal(reconnectDelayMs(5), 30000);
  assert.equal(reconnectDelayMs(9), 30000);
  assert.notEqual(reconnectDelayMs(0), reconnectDelayMs(1));
});
