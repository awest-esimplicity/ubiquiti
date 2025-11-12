/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./src/**/*.{astro,html,js,jsx,ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: "#0b1224",
          light: "#111b36",
        },
        border: {
          DEFAULT: "rgba(148, 163, 184, 0.25)",
        },
        brand: {
          blue: "#38bdf8",
          purple: "#6366f1",
        },
        status: {
          locked: "#f87171",
          unlocked: "#34d399",
        },
      },
      boxShadow: {
        card: "0 20px 45px rgba(15, 23, 42, 0.45)",
      },
    },
  },
  plugins: [],
};
