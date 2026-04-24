"use client";

/**
 * Sign-in button — triggers the Microsoft Entra ID OAuth flow via NextAuth.
 * Renders a branded button that calls signIn('microsoft-entra-id').
 * The user is redirected to Entra, then back to the configured callback URL.
 */

import { signIn } from "next-auth/react";

interface Props {
  /** Optional CSS class overrides for the button. */
  className?: string;
}

export function SignInButton({ className }: Props) {
  return (
    <button
      type="button"
      onClick={() => signIn("microsoft-entra-id")}
      className={
        className ??
        "px-5 py-2.5 rounded-md text-white font-semibold text-sm transition-colors"
      }
      style={{ backgroundColor: "var(--brand-primary)" }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.backgroundColor =
          "var(--brand-hover)")
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.backgroundColor =
          "var(--brand-primary)")
      }
    >
      Đăng nhập bằng Microsoft
    </button>
  );
}
