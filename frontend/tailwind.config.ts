import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontSize: {
        xs: ["0.85rem", { lineHeight: "1.1rem" }],
        sm: ["0.975rem", { lineHeight: "1.35rem" }],
        base: ["1.1rem", { lineHeight: "1.6rem" }],
        lg: ["1.225rem", { lineHeight: "1.85rem" }],
        xl: ["1.35rem", { lineHeight: "1.85rem" }],
        "2xl": ["1.6rem", { lineHeight: "2.1rem" }],
        "3xl": ["1.975rem", { lineHeight: "2.35rem" }],
        "4xl": ["2.35rem", { lineHeight: "2.6rem" }],
        "5xl": ["3.1rem", { lineHeight: "1" }],
        "6xl": ["3.85rem", { lineHeight: "1" }],
        "7xl": ["4.6rem", { lineHeight: "1" }],
        "8xl": ["6.1rem", { lineHeight: "1" }],
        "9xl": ["8.1rem", { lineHeight: "1" }],
      },
      colors: {
        // Brand palette — primary color #253956
        brand: {
          DEFAULT: "#253956",
          foreground: "#ffffff",
          hover: "#1b2a40",
          subtle: "#eef1f6",
        },
      },
    },
  },
  plugins: [],
};

export default config;
