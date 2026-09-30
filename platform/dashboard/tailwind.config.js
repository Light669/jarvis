/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      colors: {
        bg: { DEFAULT: "#0a0a0b", subtle: "#111113", muted: "#18181b", raised: "#1c1c20" },
        line: { DEFAULT: "#232327", strong: "#2e2e34" },
        ink: { DEFAULT: "#fafafa", muted: "#a1a1aa", subtle: "#71717a" },
        accent: { DEFAULT: "#818cf8", strong: "#6366f1", subtle: "rgba(129,140,248,0.12)" },
      },
    },
  },
  plugins: [],
};
