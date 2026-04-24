/**
 * SSE stream parser for POST-based Server-Sent Events.
 *
 * Consumes a ReadableStream<Uint8Array> (from fetch response.body) and
 * yields parsed {event, data} objects via async generator.
 *
 * Handles partial chunks split across multiple reads and keep-alive
 * comment lines (lines starting with ':').
 *
 * Usage:
 *   const res = await fetch(url, { method: 'POST', ... });
 *   for await (const evt of parseSseStream(res.body!)) {
 *     console.log(evt.event, evt.data);
 *   }
 */

export interface SseEvent {
  event: string;
  data: string;
}

/**
 * Async generator that reads an SSE stream and yields typed events.
 * Events without an "event:" field are skipped (they are comment/keep-alive
 * lines or bare data: lines, which we don't use in this protocol).
 */
export async function* parseSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Accumulate decoded bytes; stream:true keeps partial multi-byte chars
      buffer += decoder.decode(value, { stream: true });

      // Events are separated by double-newline (\n\n)
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const rawEvent = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        const parsed: Partial<SseEvent> = {};

        for (const line of rawEvent.split("\n")) {
          if (line.startsWith(":")) {
            // Comment / keep-alive — skip
            continue;
          } else if (line.startsWith("event:")) {
            parsed.event = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            // Concatenate multi-line data fields
            parsed.data = (parsed.data ?? "") + line.slice(5).trim();
          }
        }

        // Only yield if we have both event and data
        if (parsed.event && parsed.data !== undefined) {
          yield parsed as SseEvent;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
