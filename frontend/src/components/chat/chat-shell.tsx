"use client";

/**
 * ChatShell — shared chat container used by both /chat (internal) and /ask (external).
 * Composes: MessageList + ChatInput + NewSessionButton + error display.
 * Reads idToken from session for internal mode only.
 */

import { useChatStream } from "@/hooks/use-chat-stream";
import { useSession } from "@/hooks/use-session";
import { MessageList } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { NewSessionButton } from "@/components/chat/new-session-button";

interface ChatShellProps {
  endpoint: string;
  mode: "internal" | "external";
}

const PRIVACY_NOTICE =
  "Tin nhắn trò chuyện được ghi lại để cải thiện chất lượng và phân tích. Thời gian lưu trữ: 90 ngày. Vui lòng không chia sẻ thông tin bảo mật.";

export function ChatShell({ endpoint, mode }: ChatShellProps) {
  const { idToken } = useSession();

  const { messages, sources, isStreaming, error, send, reset } = useChatStream({
    endpoint,
    mode,
    idToken: mode === "internal" ? idToken : null,
  });

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Top bar: privacy notice + new chat button */}
      <div
        className="flex flex-col sm:flex-row items-start sm:items-center justify-between
          gap-2 px-4 py-2 border-b border-gray-200 bg-brand-subtle shrink-0"
      >
        <p className="text-xs text-gray-500 leading-snug max-w-prose">
          {PRIVACY_NOTICE}
        </p>
        <NewSessionButton onReset={reset} disabled={isStreaming} />
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="px-4 py-2 bg-red-50 border-b border-red-200 text-sm text-red-700 shrink-0"
        >
          {error}
          <button
            type="button"
            onClick={() => reset()}
            className="ml-3 underline text-xs"
          >
            Xóa
          </button>
        </div>
      )}

      {/* Message list — fills remaining height */}
      <MessageList
        messages={messages}
        sources={sources}
        isStreaming={isStreaming}
      />

      {/* Sticky input at bottom */}
      <ChatInput
        onSend={send}
        disabled={isStreaming}
        placeholder={
          mode === "internal"
            ? "Đặt câu hỏi về HR…"
            : "Đặt câu hỏi về chính sách…"
        }
      />
    </div>
  );
}
