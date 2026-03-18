/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./layouts/**/*.html", "./content/**/*.md"],
  theme: {
    extend: {
      colors: {
        orange: {
          DEFAULT: "#F26522",
          tint: "#FFFAF8",
        },
        yellow: {
          DEFAULT: "#FFC20E",
          tint: "#FBF9F4",
        },
        green: {
          DEFAULT: "#37A99C",
          tint: "#F5FBFA",
        },
        "pale-blue": {
          DEFAULT: "#DCEBF9",
          tint: "#F5FAFF",
        },
        dark: "#1a1a1a",
        "gray-light": "#E5E5E5",
      },
      fontFamily: {
        heading: ["'Lora'", "serif"],
        body: ["'Roboto Slab'", "serif"],
      },
      fontSize: {
        xs: "0.75rem",
        sm: "0.875rem",
        base: "1rem",
        lg: "1.125rem",
        xl: "1.25rem",
        "2xl": "1.5rem",
        "3xl": "1.875rem",
        "4xl": "2.25rem",
      },
    },
  },
  plugins: [],
};
