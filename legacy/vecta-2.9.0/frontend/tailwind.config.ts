import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Design tokens taken directly from the VECTA Sports 2026 deck (spec Section 09)
        "deep-navy": "#181B33",   // dark hero surfaces, cover-style screens, dark-mode background
        "panel-navy": "#222545",  // cards, panels, tables, contact blocks on dark surfaces
        accent: "#2563EB",        // the single accent — highlights, rules, active states, Priority markers
        "light-grey": "#D4D8DD",  // light-mode page background
        "card-grey": "#C7CBD3",   // cards/framed panels on light surfaces
        ink: "#17181C",           // primary text, light mode
        paper: "#FFFFFF",         // primary text, dark mode
        risk: {
          low: "#3FA772",
          medium: "#D9A441",
          high: "#D65A50",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "sans-serif"],
        display: ["var(--font-poppins)", "Poppins", "sans-serif"],
        body: ["var(--font-inter)", "Inter", "sans-serif"],
      },
      fontWeight: {
        light: "300",
        normal: "400",
        medium: "500",
        bold: "700",
      },
    },
  },
  plugins: [],
};
export default config;
