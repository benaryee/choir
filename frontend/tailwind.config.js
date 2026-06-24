/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        voice: {
          soprano: "#e11d48",
          alto: "#7c3aed",
          tenor: "#0891b2",
          bass: "#15803d",
          full: "#d97706",
        },
      },
    },
  },
  plugins: [],
};
