/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Norse-inspired color palette
        sindri: {
          50: '#f5f7fa',
          100: '#ebeef3',
          200: '#d2dae6',
          300: '#aab9cf',
          400: '#7d93b4',
          500: '#5c749b',
          600: '#485d81',
          700: '#3c4d69',
          800: '#354258',
          900: '#2f394b',
          950: '#1f2532',
        },
        forge: {
          50: '#fdf4f3',
          100: '#fce8e5',
          200: '#fad4cf',
          300: '#f5b5ac',
          400: '#ed887c',
          500: '#e15e50',
          600: '#cc4234',
          700: '#ab3429',
          800: '#8e2e26',
          900: '#762c25',
          950: '#40130f',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
