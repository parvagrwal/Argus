import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        forest: {
          DEFAULT: "#022B1F",
          deep: "#041F13",
          track: "#021D15",
        },
        green: {
          primary: "#0B6839",
          jungle: "#075029",
        },
        gold: {
          DEFAULT: "#F4C93B",
          light: "#FEE101",
          dim: "#EDD723",
        },
        pink: {
          neon: "#FF0080",
          light: "#FF2A85",
        },
        cream: "#FFFBE8",
        sage: "#8EB89B",
        ink: "#111111",
      },
      fontFamily: {
        sans: ["var(--font-figtree)", "sans-serif"],
        heading: ["var(--font-space-grotesk)", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
        serif: ["var(--font-fraunces)", "serif"],
      },
      backgroundImage: {
        "gauge-gradient": "linear-gradient(90deg, #8EB89B 0%, #F4C93B 50%, #FF0080 100%)",
        "radial-glow": "radial-gradient(circle, rgba(11, 104, 57, 0.4) 0%, rgba(2, 43, 31, 0) 70%)",
      },
      keyframes: {
        aurora: {
          "0%, 100%": {
            transform: "translateY(0) scale(1)",
            opacity: "0.4",
          },
          "50%": {
            transform: "translateY(-20px) scale(1.08)",
            opacity: "0.8",
          },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.6", transform: "scale(1.05)" },
        },
      },
      animation: {
        aurora: "aurora 14s ease-in-out infinite",
        pulseGlow: "pulseGlow 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
