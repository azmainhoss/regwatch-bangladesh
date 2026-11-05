/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./features/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f6fa",
          100: "#e0edf5",
          200: "#bad7eb",
          300: "#80b6db",
          400: "#3e90c7",
          500: "#1b73ad",
          600: "#10598f",
          700: "#0c4673",
          800: "#0b3c61",
          900: "#0c3352",
          950: "#062035",
        },
        slate: {
          850: "#172033",
          950: "#0b0f19",
        }
      },
      fontFamily: {
        sans: ["var(--font-inter)", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      }
    },
  },
  plugins: [],
}
