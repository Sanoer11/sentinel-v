import type { Config } from 'tailwindcss';

// Sentinel-V palette: colours are CSS variables (app/globals.css) so the dark/light toggle is one attribute.
// ink = night-time tower cab, signal = the "listening" teal, red/amber = the only two alert levels.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: v('ink'), panel: v('panel'), panel2: v('panel2'), line: v('line'),
        text: v('text'), dim: v('dim'), faint: v('faint'),
        signal: v('signal'), red: v('red'), amber: v('amber'), green: v('green'), blue: v('blue'), violet: v('violet'),
        strip: v('strip'),
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'Menlo', 'monospace'],
      },
      maxWidth: { page: '1280px' },
    },
  },
  plugins: [],
};
export default config;
