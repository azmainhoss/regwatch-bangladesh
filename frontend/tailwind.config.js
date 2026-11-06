/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./features/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Visual Direction 04: Deep Teal + Turquoise
        tealNavy: {
          950: "#101B24", // Deep navy-teal background
          900: "#142A32", // Dark teal cards
          850: "#19313A", // Elevated surface
          800: "#203B44", // Secondary surface
          700: "#29464E", // Border
          600: "#365963",
          500: "#497480",
        },
        turquoise: {
          DEFAULT: "#2DD4BF", // Primary accent
          bright: "#5EEAD4",  // Bright turquoise highlight
          soft: "#99F6E4",    // Soft teal
          dark: "#134E4A",    // Deep teal accent
          50: "#F0FDFA",
          100: "#CCFBF1",
          200: "#99F6E4",
          300: "#5EEAD4",
          400: "#2DD4BF",
          500: "#14B8A6",
          600: "#0D9488",
          700: "#0F766E",
          800: "#115E59",
          900: "#134E4A",
          950: "#042F2E",
        },
        semantic: {
          success: "#34D399",
          warning: "#FBBF24",
          danger: "#F87171",
          info: "#60A5FA",
        }
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "Courier New", "monospace"],
      }
    },
  },
  plugins: [],
}
