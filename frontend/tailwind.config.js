/** @type {import('tailwindcss').Config} */

// Every colour is a CSS variable (space-separated RGB) defined in index.css for the dark
// and light themes, so `bg-primary/20` style opacity modifiers keep working in both.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surface: token("surface"),
        "surface-container-lowest": token("surface-container-lowest"),
        "surface-container-low": token("surface-container-low"),
        "surface-container": token("surface-container"),
        "surface-container-high": token("surface-container-high"),
        "surface-container-highest": token("surface-container-highest"),
        "surface-variant": token("surface-container-highest"),
        background: token("surface"),

        primary: token("primary"),
        "primary-container": token("primary-container"),
        "on-primary": token("on-primary"),
        "on-primary-container": token("on-primary-container"),

        secondary: token("secondary"),
        "secondary-container": token("secondary-container"),
        "on-secondary": token("on-secondary"),

        tertiary: token("tertiary"),
        "tertiary-container": token("tertiary-container"),

        "on-surface": token("on-surface"),
        "on-surface-variant": token("on-surface-variant"),
        outline: token("outline"),
        "outline-variant": token("outline-variant"),

        success: token("success"),
        warning: token("warning"),
        error: token("danger"),
        danger: token("danger"),
        "error-container": token("danger-container"),
        xp: token("xp"),
        streak: token("streak"),

        "accent-rose": token("accent-rose"),
        "accent-orange": token("accent-orange"),
        "accent-amber": token("accent-amber"),
        "accent-emerald": token("accent-emerald"),
        "accent-sky": token("accent-sky"),
        "accent-violet": token("accent-violet"),
        "accent-pink": token("accent-pink"),
        "accent-teal": token("accent-teal"),
      },
      fontFamily: {
        sans: ["Hind Siliguri", "Inter", "Noto Sans Bengali", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "Hind Siliguri", "Inter", "sans-serif"],
        headline: ["Space Grotesk", "Hind Siliguri", "Inter", "sans-serif"],
        body: ["Hind Siliguri", "Inter", "Noto Sans Bengali", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        code: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "0.375rem",
        lg: "0.625rem",
        xl: "0.875rem",
        "2xl": "1.125rem",
        "3xl": "1.5rem",
        full: "9999px",
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--primary) / 0.25), 0 8px 30px -6px rgb(var(--primary) / 0.35)",
        "glow-sm": "0 0 18px -4px rgb(var(--primary) / 0.45)",
        "glow-violet": "0 0 0 1px rgb(var(--secondary) / 0.25), 0 8px 30px -6px rgb(var(--secondary) / 0.35)",
        lift: "0 10px 34px -12px rgb(var(--shadow-color) / 0.55)",
challenge: "0 1px 0 0 rgb(var(--on-surface) / 0.04)",
      },
      keyframes: {
        "fade-up": { from: { opacity: 0, transform: "translateY(14px)" }, to: { opacity: 1, transform: "none" } },
        "fade-in": { from: { opacity: 0 }, to: { opacity: 1 } },
        "scale-in": { from: { opacity: 0, transform: "scale(.94)" }, to: { opacity: 1, transform: "none" } },
        "slide-in": { from: { opacity: 0, transform: "translateX(-10px)" }, to: { opacity: 1, transform: "none" } },
        pop: { "0%": { transform: "scale(.8)", opacity: 0 }, "60%": { transform: "scale(1.08)", opacity: 1 }, "100%": { transform: "scale(1)" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgb(var(--primary) / 0.45)" },
          "50%": { boxShadow: "0 0 0 10px rgb(var(--primary) / 0)" },
        },
        "flame-flicker": {
          "0%, 100%": { transform: "scale(1) rotate(-2deg)", opacity: 1 },
          "50%": { transform: "scale(1.12) rotate(2deg)", opacity: 0.88 },
        },
        float: { "0%, 100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-7px)" } },
        blink: { "0%, 45%": { opacity: 1 }, "50%, 95%": { opacity: 0 } },
        "gradient-pan": { "0%, 100%": { backgroundPosition: "0% 50%" }, "50%": { backgroundPosition: "100% 50%" } },
        "sheen-sweep": { "0%": { transform: "translateX(-120%) skewX(-18deg)" }, "60%, 100%": { transform: "translateX(320%) skewX(-18deg)" } },
        "count-up": { from: { opacity: 0, transform: "translateY(6px)" }, to: { opacity: 1, transform: "none" } },
        burst: { "0%": { transform: "scale(.4)", opacity: 0.55 }, "100%": { transform: "scale(2.4)", opacity: 0 } },
        rise: { "0%": { transform: "translateY(8px)", opacity: 0 }, "25%": { opacity: 1 }, "100%": { transform: "translateY(-34px)", opacity: 0 } },
        "toast-in": { from: { opacity: 0, transform: "translateX(24px) scale(.96)" }, to: { opacity: 1, transform: "none" } },
        "spark-fall": { "0%": { transform: "translateY(-10px) rotate(0deg)", opacity: 0 }, "15%": { opacity: 1 }, "100%": { transform: "translateY(180px) rotate(220deg)", opacity: 0 } },
      },
      animation: {
        "fade-up": "fade-up .5s cubic-bezier(.22,1,.36,1) both",
        "fade-in": "fade-in .4s ease both",
        "scale-in": "scale-in .35s cubic-bezier(.22,1,.36,1) both",
        "slide-in": "slide-in .35s cubic-bezier(.22,1,.36,1) both",
        pop: "pop .45s cubic-bezier(.22,1,.36,1) both",
        shimmer: "shimmer 1.6s infinite",
        "glow-pulse": "glow-pulse 2.4s ease-out infinite",
        "flame-flicker": "flame-flicker 1.6s ease-in-out infinite",
        float: "float 5s ease-in-out infinite",
        blink: "blink 1.1s step-end infinite",
        "gradient-pan": "gradient-pan 7s ease infinite",
        "sheen-sweep": "sheen-sweep 2.8s ease-in-out infinite",
        burst: "burst .9s cubic-bezier(.22,1,.36,1) forwards",
        rise: "rise 1.4s ease-out forwards",
        "toast-in": "toast-in .4s cubic-bezier(.22,1,.36,1) both",
        "spark-fall": "spark-fall 1.6s ease-in forwards",
      },
      backgroundImage: {
        "grid-fade": "linear-gradient(to bottom, rgb(var(--surface) / 0), rgb(var(--surface) / 1))",
      },
    },
  },
  plugins: [],
};
