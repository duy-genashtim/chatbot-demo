"use client";

/**
 * Chat input — textarea + send button.
 * Enter = send, Shift+Enter = newline.
 * Disabled while streaming. Auto-focuses on mount.
 */

import { useRef, useEffect, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Đặt câu hỏi…",
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSend = () => {
    const value = textareaRef.current?.value.trim();
    if (!value || disabled) return;
    onSend(value);
    if (textareaRef.current) textareaRef.current.value = "";
    // Reset height after clear
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea height as user types
  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  return (
    <div className="flex items-end gap-2 p-3 border-t border-gray-200 bg-white">
      <textarea
        ref={textareaRef}
        rows={1}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Nhập tin nhắn"
        className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2
          text-sm text-gray-900 placeholder:text-gray-400 bg-white leading-relaxed
          focus:outline-none focus:ring-2 focus:ring-brand focus:border-transparent
          disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed
          max-h-40 overflow-y-auto"
      />
      <Button
        variant="brand"
        size="md"
        onClick={handleSend}
        disabled={disabled}
        aria-label="Gửi tin nhắn"
        className="shrink-0 self-end"
      >
        Gửi
      </Button>
    </div>
  );
}
