// Authenticated SSE over fetch: EventSource cannot send the Bearer header.
// Reconnects with the last notification id; the server replays unread items.

import { streamUrl } from "../api/stream-api";
import { apiLocale } from "../i18n";
import { getAccessToken, refreshTokens } from "./oauth";

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
  id?: string;
}

let controller: AbortController | null = null;
let lastNotificationId: string | null = null;

function parseBlock(block: string): StreamEvent | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("id:")) id = line.slice(3).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (data.length === 0) return null;
  try {
    return { event, id, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
  } catch {
    return null;
  }
}

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function connect(onEvent: (event: StreamEvent) => void, signal: AbortSignal) {
  while (!signal.aborted) {
    const token = getAccessToken();
    if (!token) {
      await sleep(2000);
      continue;
    }
    try {
      const res = await fetch(streamUrl(lastNotificationId), {
        headers: {
          Authorization: `Bearer ${token}`,
          "Accept-Language": apiLocale(),
        },
        signal,
      });
      if (res.status === 401) {
        await refreshTokens();
        continue;
      }
      if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let index = buffer.indexOf("\n\n");
        while (index >= 0) {
          const block = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          const event = parseBlock(block);
          if (event) {
            if (event.id && event.event === "notification.created") {
              lastNotificationId = event.id;
            }
            onEvent(event);
          }
          index = buffer.indexOf("\n\n");
        }
      }
    } catch (e) {
      if (signal.aborted) return;
      // Network hiccup or server restart: reconnect with backoff.
      await sleep(2000);
    }
  }
}

export function startEventStream(onEvent: (event: StreamEvent) => void): () => void {
  stopEventStream();
  controller = new AbortController();
  const { signal } = controller;
  void connect(onEvent, signal);
  return () => {
    controller?.abort();
    controller = null;
  };
}

export function stopEventStream(): void {
  controller?.abort();
  controller = null;
}
