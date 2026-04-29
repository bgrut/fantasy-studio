/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
  	extend: {
  		colors: {
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			teal: 'hsl(var(--teal))',
  			gold: 'hsl(var(--gold))',
  			sidebar: {
  			 DEFAULT: 'hsl(var(--sidebar, var(--card)))',
  			 foreground: 'hsl(var(--sidebar-foreground, var(--foreground)))',
  			 primary: 'hsl(var(--sidebar-primary, var(--primary)))',
  			 'primary-foreground': 'hsl(var(--sidebar-primary-foreground, var(--primary-foreground)))',
  			 accent: 'hsl(var(--sidebar-accent, var(--accent)))',
  			 'accent-foreground': 'hsl(var(--sidebar-accent-foreground, var(--accent-foreground)))',
  			 border: 'hsl(var(--sidebar-border, var(--border)))',
  			 ring: 'hsl(var(--sidebar-ring, var(--ring)))'
  			},
  			chart: {
  				'1': 'hsl(var(--chart-1, 253 100% 68%))',
  				'2': 'hsl(var(--chart-2, 342 100% 68%))',
  				'3': 'hsl(var(--chart-3, 168 62% 53%))',
  				'4': 'hsl(var(--chart-4, 40 100% 67%))',
  				'5': 'hsl(var(--chart-5, 252 13% 55%))'
  			}
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		fontFamily: {
  			sans: ['Outfit', 'sans-serif'],
  			// v1.4 close-out — Cabinet Grotesk for hero + key callouts.
  			// Geometric/wide, GameCube-cinematic, closest free analogue to
  			// Surgena. If Surgena gets licensed, prepend it here.
  			display: ['"Cabinet Grotesk"', '"General Sans"', 'Outfit', 'sans-serif'],
  			mono: ['JetBrains Mono', 'monospace']
  		},
  		boxShadow: {
  			// v1.4 polish — elevation tokens. Class equivalents in index.css.
  			'elevation-1': 'inset 0 1px 0 rgba(255,255,255,0.04), 0 1px 2px rgba(0,0,0,0.25)',
  			'elevation-2': 'inset 0 1px 0 rgba(255,255,255,0.05), 0 8px 30px -8px rgba(0,0,0,0.5), 0 0 24px -8px rgba(124,92,255,0.15)',
  			'elevation-3': 'inset 0 1px 0 rgba(255,255,255,0.06), 0 25px 60px -15px rgba(0,0,0,0.6), 0 0 40px -10px rgba(255,92,138,0.2)',
  			'video-brand': '-16px -10px 50px -20px rgba(124,92,255,0.35), 20px 18px 60px -18px rgba(255,92,138,0.32), 0 30px 60px -25px rgba(0,0,0,0.7)'
  		},
  		animation: {
  			'fade-in': 'fade-in 0.5s ease-out',
  			'slide-up': 'slide-up 0.5s ease-out',
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		},
  		keyframes: {
  			'fade-in': {
  				'0%': {
  					opacity: '0'
  				},
  				'100%': {
  					opacity: '1'
  				}
  			},
  			'slide-up': {
  				'0%': {
  					transform: 'translateY(10px)',
  					opacity: '0'
  				},
  				'100%': {
  					transform: 'translateY(0)',
  					opacity: '1'
  				}
  			},
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
}
