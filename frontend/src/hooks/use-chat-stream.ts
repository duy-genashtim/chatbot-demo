"use client";

/**
 * SSE chat streaming hook.
 *
 * Uses native fetch + ReadableStream (NOT EventSource — EventSource only
 * supports GET; our backend requires POST with JSON body).
 *
 * Event protocol (from phase-05):
 *   event: sources  data: [{source, section}, ...]
 *   event: delta    data: {text: "..."}
 *   event: done     data: {session_id: "...", latency_ms: N}
 *   event: error    data: {message: "..."}
 */

import { useState, useCallback, useRef } from "react";
import { parseSseStream } from "@/lib/sse-parser";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export interface Source {
  source: string;
  section?: string;
}

export interface UseChatStreamOptions {
  endpoint: string;
  mode: "internal" | "external";
  /** Only attached for internal mode. Never sent to external endpoint. */
  idToken?: string | null;
}

export interface UseChatStreamResult {
  messages: Message[];
  sources: Source[] | null;
  isStreaming: boolean;
  error: string | null;
  sessionId: string | null;
  send: (text: string) => Promise<void>;
  reset: () => void;
}

function makeId(): string {
  return Math.random().toString(36).slice(2, 10);
}

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000/api";

export function useChatStream({
  endpoint,
  mode,
  idToken,
}: UseChatStreamOptions): UseChatStreamResult {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sources, setSources] = useState<Source[] | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Ref to the current assistant message id so we can append deltas
  const assistantIdRef = useRef<string | null>(null);

  const send = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      setError(null);
      setSources(null);
      setIsStreaming(true);

      // Push user message immediately
      const userMsg: Message = { id: makeId(), role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);

      // Reset assistant bubble tracker
      assistantIdRef.current = null;

      const url = `${BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };

      // Only attach Authorization header for internal mode
      if (mode === "internal" && idToken) {
        headers["Authorization"] = `Bearer ${idToken}`;
      }

      try {
        const res = await fetch(url, {
          method: "POST",
          headers,
          // Include cookies for external mode (session cookie)
          credentials: mode === "external" ? "include" : "same-origin",
          body: JSON.stringify({
            message: text,
            ...(sessionId ? { session_id: sessionId } : {}),
          }),
        });

        if (!res.ok) {
          let msg = `Yêu cầu thất bại: ${res.status}`;
          try {
            const body = await res.json();
            const raw = body?.detail ?? body?.message ?? msg;
            msg = typeof raw === "string" ? raw : JSON.stringify(raw);
          } catch {
            // ignore
          }
          setError(msg);
          setIsStreaming(false);
          return;
        }

        if (!res.body) {
          setError("Máy chủ không trả về nội dung.");
          setIsStreaming(false);
          return;
        }

        // Parse SSE events from the streaming response body
        for await (const evt of parseSseStream(res.body)) {
          switch (evt.event) {
            case "sources": {
              try {
                const parsed = JSON.parse(evt.data) as Source[];
                setSources(parsed);
              } catch {
                // malformed sources — ignore
              }
              break;
            }

            case "delta": {
              try {
                const { text: token } = JSON.parse(evt.data) as { text: string };

                if (!assistantIdRef.current) {
                  // First delta — create the assistant bubble
                  const aid = makeId();
                  assistantIdRef.current = aid;
                  setMessages((prev) => [
                    ...prev,
                    { id: aid, role: "assistant", content: token },
                  ]);
                } else {
                  // Append token to existing assistant bubble
                  const aid = assistantIdRef.current;
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === aid
                        ? { ...m, content: m.content + token }
                        : m,
                    ),
                  );
                }
              } catch {
                // malformed delta — ignore
              }
              break;
            }

            case "done": {
              try {
                const { session_id } = JSON.parse(evt.data) as {
                  session_id: string;
                  latency_ms?: number;
                };
                setSessionId(session_id);
              } catch {
                // ignore parse error
              }
              setIsStreaming(false);
              break;
            }

            case "error": {
              try {
                const { message } = JSON.parse(evt.data) as { message: string };
                setError(message);
              } catch {
                setError("Đã xảy ra lỗi.");
              }
              setIsStreaming(false);
              break;
            }

            default:
              break;
          }
        }
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "Lỗi mạng. Vui lòng thử lại.";
        setError(msg);
      } finally {
        setIsStreaming(false);
      }
    },
    [endpoint, mode, idToken, sessionId, isStreaming],
  );

  const reset = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setSources(null);
    setError(null);
    assistantIdRef.current = null;
  }, []);

  return { messages, sources, isStreaming, error, sessionId, send, reset };
}
