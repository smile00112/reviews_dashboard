/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // SERM Dashboard dark palette (docs/plans/dashboard_prototype.html :root)
        bg: "#0f1117",
        surface: "#171a23",
        "surface-2": "#1e222d",
        "surface-3": "#262b38",
        border: "#2a3041",
        text: "#e8eaf0",
        "text-dim": "#8b91a3",
        "text-faint": "#5a6175",
        accent: "#d4ff3a",
        "accent-dim": "#95b224",
        good: "#4ade80",
        warn: "#fbbf24",
        bad: "#f87171",
        info: "#60a5fa",
      },
      fontFamily: {
        sans: ["var(--font-manrope)", "system-ui", "sans-serif"],
        display: ["var(--font-fraunces)", "serif"],
        mono: ["var(--font-jetbrains)", "monospace"],
      },
    },
  },
  plugins: [],
};
