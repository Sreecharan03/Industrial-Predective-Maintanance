/** SenseMinds 360 design tokens.
 *  Palette is computationally validated (lightness band, chroma floor,
 *  colour-vision-deficiency separation dE2000 >= 12, contrast >= 3:1 on the
 *  light surface). Warm light theme — deliberately NOT the cool navy/teal
 *  "AI dashboard" cliche.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      colors: {
        // Surfaces — warm, not cool grey
        canvas: "#FBFAF9",
        card: "#FFFFFF",
        line: "#EDE9E6",
        ink: { DEFAULT: "#1C1917", soft: "#57534E", muted: "#8A817C" },

        // Brand / primary (violet — leads the categorical order)
        brand: {
          50: "#F5F1FE", 100: "#EDE5FD", 200: "#DCCCFB",
          400: "#A275F2", 500: "#8B54EF", 600: "#7C3AED", 700: "#6428C9",
        },

        // Categorical series — FIXED ORDER, never cycled (validated dE>=16.7)
        cat: {
          1: "#7C3AED", // violet
          2: "#0F9D8F", // teal
          3: "#C026D3", // fuchsia
          4: "#4D7C0F", // olive
          5: "#0284C7", // cyan
        },

        // Status — RESERVED, never reused as a series. Always with icon + label.
        ok: { DEFAULT: "#15803D", soft: "#E8F5EC", ring: "#BBE3C8" },
        info: { DEFAULT: "#57534E", soft: "#F1EFED", ring: "#DCD7D3" },
        warn: { DEFAULT: "#B45309", soft: "#FDF0E3", ring: "#F3D5B0" },
        crit: { DEFAULT: "#BE123C", soft: "#FDECF0", ring: "#F5C2CE" },
      },
      boxShadow: {
        soft: "0 1px 2px rgba(28,25,23,.04), 0 4px 16px -4px rgba(28,25,23,.07)",
        lift: "0 2px 4px rgba(28,25,23,.05), 0 12px 32px -8px rgba(28,25,23,.12)",
      },
      borderRadius: { xl2: "1.125rem" },
      keyframes: {
        rise: { "0%": { opacity: 0, transform: "translateY(6px)" }, "100%": { opacity: 1, transform: "none" } },
      },
      animation: { rise: "rise .35s cubic-bezier(.22,.9,.3,1) both" },
    },
  },
  plugins: [],
};
