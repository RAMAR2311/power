/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        power: {
          dark: '#000000',
          card: '#0d1117',
          border: '#21262d',
          white: '#FFFFFF',
          red: '#E31313',
          green: '#40A435',
          blue: '#029CC2'
        }
      },
      fontFamily: {
        brand: ['Ethnocentric', 'Orbitron', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif']
      }
    }
  }
}
