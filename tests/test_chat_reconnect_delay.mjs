import assert from "node:assert/strict";
import test from "node:test";

import { acceptToken, outboundEvent } from "../uis/knowledge/chat_protocol.js";
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

test("a message during a live reply aborts, and tokens wait for the checkpoint", () => {
  assert.deepEqual(outboundEvent(false, "What is Brasa Points?"), {
    event: "support_user_message",
    content: "What is Brasa Points?",
  });
  assert.deepEqual(outboundEvent(true, "Stop and answer allergens"), {
    event: "interrupt",
    new_input: "Stop and answer allergens",
  });
  assert.equal(acceptToken(false), false);
  assert.equal(acceptToken(true), true);
});
