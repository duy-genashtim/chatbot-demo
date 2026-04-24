"use client";

/**
 * Typing indicator — three-dot pulse animation shown while the assistant
 * is streaming but no tokens have arrived yet (isStreaming + empty content).
 */

export function TypingIndicator() {
  return (
    <div
      className="flex items-center gap-1 px-4 py-3"
      role="status"
      aria-label="Trợ lý đang nhập"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-brand opacity-60 animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}
