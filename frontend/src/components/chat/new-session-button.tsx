"use client";

/**
 * New session button — clears local chat state and forgets the session_id.
 * Calls the reset() callback from useChatStream.
 */

import { Button } from "@/components/ui/button";

interface NewSessionButtonProps {
  onReset: () => void;
  disabled?: boolean;
}

export function NewSessionButton({ onReset, disabled = false }: NewSessionButtonProps) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onReset}
      disabled={disabled}
      aria-label="Bắt đầu cuộc trò chuyện mới"
      title="Bắt đầu cuộc trò chuyện mới"
    >
      + Trò chuyện mới
    </Button>
  );
}
