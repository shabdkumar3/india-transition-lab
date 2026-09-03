import type { Config } from "tailwindcss";

/**
 * India Steel Transition — design tokens.
 *
 * Editorial, climate-tech product palette:
 *   - paper   : warm near-white surfaces (not blue-grey dashboard grey)
 *   - ink     : warm neutral text scale
 *   - steel   : deep steel blue (primary / BF-BOF)
 *   - teal    : hydrogen accent
 *   - green   : recycled scrap accent
 *   - copper  : coal routes (burnt orange)
 * Technology colors are consistent everywhere via TECH_COLORS in Charts.tsx.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        /* CSS-variable semantic tokens */
        background:  "var(--background)",
        foreground:  "var(--foreground)",
        card: {
          DEFAULT:    "var(--card)",
          foreground: "var(--card-foreground)",
        },
        border:      "var(--border)",
        muted: {
          DEFAULT:    "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        primary: {
          DEFAULT:    "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        paper: {
          DEFAULT: "#f7f6f2",
          deep: "#f1efe9",
          card: "#ffffff",
        },
        ink: {
          50: "#f7f7f5",
          100: "#ecece8",
          200: "#dcddd6",
          300: "#bfc1b8",
          400: "#9a9d93",
          500: "#7a7e74",
          600: "#5e6359",
          700: "#474c44",
          800: "#333830",
          900: "#23261f",
          950: "#14160f",
        },
        steel: {
          50: "#f0f6fb",
          100: "#dcebf6",
          200: "#b9d7ec",
          300: "#86badb",
          400: "#4e97c4",
          500: "#2f7bb0",
          600: "#226093",
          700: "#1d4f7a",
          800: "#1a4266",
          900: "#163551",
          950: "#0d2133",
        },
        teal: {
          50: "#effaf9",
          100: "#d3f2f0",
          200: "#a7e4e2",
          300: "#6fcfce",
          400: "#3db3b3",
          500: "#249798",
          600: "#1a7c7e",
          700: "#186566",
          800: "#175153",
          900: "#164345",
        },
        green: {
          50: "#f0f7f1",
          100: "#dceddf",
          200: "#bcdcc3",
          300: "#90c39c",
          400: "#60a472",
          500: "#428757",
          600: "#316c45",
          700: "#285739",
          800: "#22462f",
          900: "#1c3a28",
        },
        copper: {
          50: "#fbf3ec",
          100: "#f5e2d1",
          200: "#e9c3a1",
          300: "#db9c6b",
          400: "#cf7d44",
          500: "#c0642e",
          600: "#a24e25",
          700: "#833d20",
          800: "#6a3320",
          900: "#572c1d",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        display: [
          "Inter",
          "SF Pro Display",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      letterSpacing: {
        tightest: "-0.045em",
      },
      boxShadow: {
        card: "0 1px 2px rgba(20,26,34,0.04), 0 4px 16px rgba(20,26,34,0.05)",
        lift: "0 2px 4px rgba(20,26,34,0.05), 0 12px 32px rgba(20,26,34,0.10)",
      },
    },
  },
  plugins: [],
};

export default config;
