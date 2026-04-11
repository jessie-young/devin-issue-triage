/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ["class"],
    content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
  	extend: {
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		colors: {
  			nasa: {
  				navy: '#0b1120',
  				dark: '#111827',
  				panel: '#1a2332',
  				border: '#1e3a5f',
  				cyan: '#06b6d4',
  				teal: '#14b8a6',
  				amber: '#f59e0b',
  				green: '#22c55e',
  				red: '#ef4444',
  				muted: '#64748b',
  				text: '#e2e8f0',
  			}
  		},
  		fontFamily: {
  			mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
  			sans: ['Inter', 'system-ui', 'sans-serif'],
  		},
  		animation: {
  			'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
  			'scan-line': 'scan-line 3s linear infinite',
  			'fade-in': 'fade-in 0.5s ease-out',
  		},
  		keyframes: {
  			'pulse-glow': {
  				'0%, 100%': { boxShadow: '0 0 5px rgba(6, 182, 212, 0.3)' },
  				'50%': { boxShadow: '0 0 20px rgba(6, 182, 212, 0.6), 0 0 40px rgba(6, 182, 212, 0.2)' },
  			},
  			'scan-line': {
  				'0%': { transform: 'translateY(-100%)' },
  				'100%': { transform: 'translateY(100%)' },
  			},
  			'fade-in': {
  				'0%': { opacity: '0', transform: 'translateY(10px)' },
  				'100%': { opacity: '1', transform: 'translateY(0)' },
  			},
  		},
  	}
  },
  plugins: [import("tailwindcss-animate")],
}

