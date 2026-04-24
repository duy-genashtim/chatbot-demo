"use client";

/**
 * Input primitive — single-line text input, Tailwind-based.
 */

import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Optional error state styling */
  hasError?: boolean;
}

export function Input({ hasError = false, className = "", ...props }: InputProps) {
  return (
    <input
      className={[
        "w-full rounded-md border px-3 py-2 text-sm text-gray-900",
        "placeholder:text-gray-400 bg-white",
        "focus:outline-none focus:ring-2 focus:ring-brand focus:border-transparent",
        "disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed",
        hasError
          ? "border-red-400 focus:ring-red-400"
          : "border-gray-300",
        className,
      ].join(" ")}
      {...props}
    />
  );
}
