"use client";

/**
 * Message bubble — role-aware chat message renderer.
 *
 * User messages: right-aligned, subtle brand background.
 * Assistant messages: left-aligned, white card with border.
 * Assistant content rendered via react-markdown + remark-gfm (never raw HTML).
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "@/hooks/use-chat-stream";

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-tr-sm
            bg-brand-subtle text-gray-900 text-sm leading-relaxed
            shadow-sm"
        >
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className="max-w-[80%] px-4 py-3 rounded-2xl rounded-tl-sm
          bg-white border border-gray-200 shadow-sm
          text-sm leading-relaxed text-gray-900"
      >
        <div className="prose prose-sm prose-gray max-w-none
          prose-p:my-1 prose-headings:mt-3 prose-headings:mb-1
          prose-code:bg-gray-100 prose-code:px-1 prose-code:rounded
          prose-pre:bg-gray-100 prose-pre:rounded-md prose-pre:p-3">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
