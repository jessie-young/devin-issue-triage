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
  			app: {
  				bg: '#f8fafc',
  				surface: '#ffffff',
  				panel: '#f1f5f9',
  				border: '#e2e8f0',
  				'border-light': '#f1f5f9',
  				primary: '#4f46e5',
  				'primary-hover': '#4338ca',
  				'primary-light': '#eef2ff',
  				success: '#059669',
  				'success-light': '#ecfdf5',
  				warning: '#d97706',
  				'warning-light': '#fffbeb',
  				danger: '#dc2626',
  				'danger-light': '#fef2f2',
  				text: '#0f172a',
  				'text-secondary': '#475569',
  				'text-muted': '#94a3b8',
  			}
  		},
  		fontFamily: {
  			mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
  			sans: ['Inter', 'system-ui', 'sans-serif'],
  		},
  		animation: {
  			'fade-in': 'fade-in 0.3s ease-out',
  			'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
  		},
  		keyframes: {
  			'fade-in': {
  				'0%': { opacity: '0', transform: 'translateY(4px)' },
  				'100%': { opacity: '1', transform: 'translateY(0)' },
  			},
  			'pulse-soft': {
  				'0%, 100%': { opacity: '1' },
  				'50%': { opacity: '0.7' },
  			},
  		},
  	}
  },
  plugins: [import("tailwindcss-animate")],
}

