/**
 * /chat — internal HR Q&A page (auth-gated).
 *
 * Server component: calls auth() and redirects to "/" if unauthenticated.
 * Renders ChatShell for the internal endpoint.
 */

import { redirect } from "next/navigation";
import { auth } from "@/lib/auth-config";
import { ChatShell } from "@/components/chat/chat-shell";

export const metadata = { title: "Hỏi đáp HR — G-HelpDesk" };

export default async function InternalChatPage() {
  const session = await auth();

  if (!session?.user) {
    redirect("/");
  }

  return (
    <div className="h-full flex flex-col max-w-3xl mx-auto w-full">
      <ChatShell endpoint="/internal/chat" mode="internal" />
    </div>
  );
}
