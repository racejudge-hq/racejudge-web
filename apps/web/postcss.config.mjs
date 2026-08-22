/**
 * Tailwind v4 ships as a PostCSS plugin, and this file is the only thing that
 * puts it in the pipeline. Without it Turbopack handles `@import "tailwindcss"`
 * itself and cannot resolve `shadcn/tailwind.css` or `tw-animate-css`, whose
 * stylesheets are published only under the `style` export condition -- which is
 * Tailwind's resolver to read, not the bundler's. Every page 500s instead.
 */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
