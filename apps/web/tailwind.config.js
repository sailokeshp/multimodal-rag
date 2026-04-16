/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50: '#f0f7ff', 500: '#3b82f6', 700: '#1d4ed8' },
      },
    },
  },
  plugins: [],
}
