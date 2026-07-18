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
        capture: {
          surface: { page: "var(--capture-surface-page)", card: "var(--capture-surface-card)", video: "var(--capture-surface-video)" },
          border: { default: "var(--capture-border-default)", strong: "var(--capture-border-strong)" },
          text: { primary: "var(--capture-text-primary)", secondary: "var(--capture-text-secondary)", muted: "var(--capture-text-muted)" },
          brand: { primary: "var(--capture-brand-primary)", soft: "var(--capture-brand-soft)" },
          status: { recording: "var(--capture-status-recording)", success: "var(--capture-status-success)", warning: "var(--capture-status-warning)", info: "var(--capture-status-info)" },
          timeline: { set: "var(--capture-timeline-set)", game: "var(--capture-timeline-game)", rally: "var(--capture-timeline-rally)", highlight: "var(--capture-timeline-highlight)", playhead: "var(--capture-timeline-playhead)", sideChange: "var(--capture-timeline-side-change)" },
        },
      },
      boxShadow: {
        glow: "0 0 42px rgba(84, 254, 73, 0.22)",
        card: "0 18px 60px rgba(0, 0, 0, 0.32)",
        "capture-card": "var(--capture-shadow-card)",
      },
    },
  },
} satisfies Config;
