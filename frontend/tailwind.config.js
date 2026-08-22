/** Approved theme (ARCH §10.1, D12) */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "islamic-teal": "#0D7377",
        "islamic-gold": "#D4AF37",
        "islamic-dark": "#1A1A2E",
        "islamic-light": "#F8F9FA",
        "deep-teal": "#14213D",
        "orange-accent": "#FCA311",
        neon: {
          green: "#10b981",
          blue: "#3b82f6",
          red: "#ef4444",
          yellow: "#facc15",
          orange: "#f59e0b",
          cyan: "#22d3ee",
          pink: "#ec4899",
          purple: "#8b5cf6",
        },
      },
      fontFamily: {
        arabic: ["'Noto Naskh Arabic'", "Amiri", "'Traditional Arabic'", "serif"],
        ui: ["'Segoe UI'", "Tahoma", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
