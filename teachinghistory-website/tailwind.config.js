/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./layouts/**/*.html", "./content/**/*.md"],
  // subsection-list.html builds `text-{{ $color }}-ink` from a template variable, so the
  // literal class name never appears in scanned content for JIT to detect on its own.
  safelist: ["text-orange-ink", "text-yellow-ink", "text-green-ink", "text-pale-blue-ink"],
  // Four layout bands use Tailwind's defaults: mobile base, sm, md, and lg.
  // xl and 2xl remain available for isolated wide-screen refinements.
  theme: {
    extend: {
      colors: {
        orange: {
          DEFAULT: "#F26522",
          tint: "#FFFAF8",
          // WCAG 2.1 AA-safe (4.5:1 on white) text variant of DEFAULT, for small text/links.
          ink: "#CE4B0C",
        },
        yellow: {
          DEFAULT: "#FFC20E",
          tint: "#FBF9F4",
          ink: "#946F00",
        },
        green: {
          DEFAULT: "#37A99C",
          tint: "#F5FBFA",
          ink: "#2A8278",
        },
        "pale-blue": {
          DEFAULT: "#DCEBF9",
          tint: "#F5FAFF",
          ink: "#2278C8",
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
