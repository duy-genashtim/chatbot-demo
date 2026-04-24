"use client";

/**
 * Sign-out button — clears the NextAuth session cookie and optionally
 * redirects to the home page after sign-out.
 */

import { signOut } from "next-auth/react";

interface Props {
  /** Optional CSS class overrides for the button. */
  className?: string;
  /** Where to redirect after sign-out. Defaults to "/". */
  callbackUrl?: string;
}

export function SignOutButton({ className, callbackUrl = "/" }: Props) {
  return (
    <button
      type="button"
      onClick={() => signOut({ callbackUrl })}
      className={
        className ??
        "px-4 py-2 rounded-md border border-white/40 text-white text-sm font-medium hover:bg-white hover:text-gray-900 transition-colors"
      }
    >
      Đăng xuất
    </button>
  );
}
