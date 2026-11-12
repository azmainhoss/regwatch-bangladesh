/** @type {import('tailwindcss').Config} */

// Every colour reads from a CSS variable holding RGB channels, so one class
// (e.g. `bg-surface`) serves both themes. Values live in app/globals.css.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

module.exports = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: token("canvas"),
        surface: token("surface"),
        sunken: token("sunken"),
        line: token("line"),
        "line-strong": token("line-strong"),
        ink: {
          DEFAULT: token("ink"),
          2: token("ink-2"),
          3: token("ink-3"),
        },
        accent: {
          DEFAULT: token("accent"),
          hover: token("accent-hover"),
          soft: token("accent-soft"),
          ink: token("accent-ink"),
        },
        ok: { DEFAULT: token("ok"), soft: token("ok-soft") },
        warn: { DEFAULT: token("warn"), soft: token("warn-soft") },
        bad: { DEFAULT: token("bad"), soft: token("bad-soft") },
        info: { DEFAULT: token("info"), soft: token("info-soft") },
        muted: { DEFAULT: token("muted"), soft: token("muted-soft") },
        marker: { DEFAULT: token("marker"), edge: token("marker-edge") },
      },
      fontFamily: {
        sans: ["var(--font-latin)", "var(--font-bangla)", "system-ui", "sans-serif"],
        bangla: ["var(--font-bangla)", "var(--font-latin)", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      borderRadius: {
        control: "6px",
        panel: "10px",
      },
      boxShadow: {
        panel: "0 1px 2px rgb(var(--shadow) / 0.06), 0 4px 16px -8px rgb(var(--shadow) / 0.12)",
        pop: "0 2px 6px rgb(var(--shadow) / 0.08), 0 24px 48px -16px rgb(var(--shadow) / 0.28)",
      },
      maxWidth: {
        prose: "68ch",
      },
    },
  },
  plugins: [],
};
