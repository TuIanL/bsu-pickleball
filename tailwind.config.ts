import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "SF Pro Display",
          "SF Pro Text",
          "Helvetica Neue",
          "Arial",
          "system-ui",
          "sans-serif",
        ],
      },
      colors: {
        court: {
          blue: "#2F80ED",
          lime: "#D9FF3F",
          green: "#13D208",
        },
      },
      boxShadow: {
        glow: "0 0 42px rgba(84, 254, 73, 0.22)",
        card: "0 18px 60px rgba(0, 0, 0, 0.32)",
      },
    },
  },
} satisfies Config;
