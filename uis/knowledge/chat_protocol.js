/** Frame to send when the manager submits text. A live reply is aborted first. */
export function outboundEvent(streaming, content) {
  if (streaming) {
    return { event: "support_interrupt", content };
  }
  return { event: "support_user_message", content };
}

/** Token frames wait until support_session has restored the thread. */
export function acceptToken(checkpointReady) {
  return checkpointReady === true;
}
