/**
 * /ask — external policy Q&A page (no auth required).
 *
 * Public page: no auth guard. Renders ChatShell for the external endpoint.
 * Session cookie is set by the backend on first request.
 */

import { ChatShell } from "@/components/chat/chat-shell";

export const metadata = { title: "Hỏi đáp chính sách — G-HelpDesk" };

export default function ExternalAskPage() {
  return (
    <div className="h-full flex flex-col max-w-3xl mx-auto w-full">
      <ChatShell endpoint="/external/chat" mode="external" />
    </div>
  );
}
