import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        zinc: {
          950: '#09090b',
        },
      },
    },
  },
  plugins: [],
}

export default config
