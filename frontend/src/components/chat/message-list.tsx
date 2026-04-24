"use client";

/**
 * Message list — scrollable container that auto-scrolls to bottom
 * whenever messages or streaming state changes.
 * Renders MessageBubble per message + TypingIndicator while streaming
 * with no assistant tokens yet. Sources card rendered above current
 * assistant bubble when sources are present.
 */

import { useEffect, useRef } from "react";
import type { Message, Source } from "@/hooks/use-chat-stream";
import { MessageBubble } from "@/components/chat/message-bubble";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { SourcesCard } from "@/components/chat/sources-card";

interface MessageListProps {
  messages: Message[];
  sources: Source[] | null;
  isStreaming: boolean;
}

export function MessageList({ messages, sources, isStreaming }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or streaming updates
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // Determine the index of the last assistant message (for sources attachment)
  const lastAssistantIdx = messages.reduce<number>(
    (acc, m, i) => (m.role === "assistant" ? i : acc),
    -1,
  );

  // Show typing indicator when streaming but last message isn't assistant yet
  const showTypingIndicator =
    isStreaming &&
    (messages.length === 0 || messages[messages.length - 1].role === "user");

  return (
    <div
      className="flex-1 overflow-y-auto px-4 py-4 space-y-3"
      role="log"
      aria-live="polite"
      aria-label="Tin nhắn trò chuyện"
    >
      {messages.length === 0 && !isStreaming && (
        <p className="text-center text-sm text-gray-400 pt-12 select-none">
          Đặt câu hỏi để bắt đầu.
        </p>
      )}

      {messages.map((msg, idx) => (
        <div key={msg.id}>
          {/* Sources card appears above the last assistant bubble */}
          {idx === lastAssistantIdx && sources && sources.length > 0 && (
            <SourcesCard sources={sources} />
          )}
          <MessageBubble message={msg} />
        </div>
      ))}

      {showTypingIndicator && (
        <div className="flex justify-start">
          <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm shadow-sm">
            <TypingIndicator />
          </div>
        </div>
      )}

      {/* Invisible scroll anchor */}
      <div ref={bottomRef} />
    </div>
  );
}
