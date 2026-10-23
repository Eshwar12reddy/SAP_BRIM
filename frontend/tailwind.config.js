/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: '#0F172A',
        cloud: '#F8FAFC',
        brand: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#334155', // Primary Slate
          600: '#1e293b',
          700: '#0f172a',
          800: '#0284c7',
          900: '#0369a1',
        },
        orange: {
          400: '#fb923c',
          500: '#f97316', // Send button accent
          600: '#ea580c',
          700: '#c2410c', // High contrast button / text
        },
        sky: {
          50: '#f0f9ff',
          100: '#e0f2fe', // Sky tint for hover and selected rows
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8', // Sky blue accent
          500: '#0ea5e9',
          600: '#0284c7', // Focus ring
          700: '#0369a1', // Links
        },
        sap: {
          50: '#f8fafc',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#38bdf8',
          400: '#0ea5e9',
          500: '#0284c7',
          600: '#334155',
          700: '#1e293b',
          800: '#0f172a',
        },
        slate: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          750: '#293548',
          800: '#1e293b',
          850: '#172033',
          900: '#0f172a',
          950: '#070a12',
        }
      },
      fontFamily: {
        sans: ['"DM Sans"', 'Inter', 'system-ui', 'sans-serif'],
        display: ['Manrope', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        'brand': '0 10px 30px -10px rgba(255, 98, 0, 0.35)',
        'brand-glow': '0 0 25px rgba(255, 98, 0, 0.45)',
      }
    },
  },
  plugins: [],
}
