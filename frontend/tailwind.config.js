/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Glass Laboratory Color Palette
        primary: {
          50: '#ecfeff',
          100: '#cffafe',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4', // Cyan - Science/Bio accent
          600: '#0891b2',
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
        },
        secondary: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#8b5cf6', // Violet - AI/Compute accent
          600: '#7c3aed',
          700: '#6d28d9',
          800: '#5b21b6',
          900: '#4c1d95',
        },
        accent: {
          teal: '#14b8a6',    // Teal accent
          sky: '#0ea5e9',     // Sky blue
          emerald: '#10b981', // Success states
          rose: '#f43f5e',    // Danger states
          amber: '#f59e0b',   // Warning states
        },
        // Gemini "Cyber-Bio" semantic colors
        bio: {
          teal: '#2DD4BF',    // Teal-400
          blue: '#3B82F6',    // Blue-500
          violet: '#8B5CF6',  // Violet-500
        },
        glass: {
          100: 'rgba(255, 255, 255, 0.1)',
          200: 'rgba(255, 255, 255, 0.2)',
          300: 'rgba(255, 255, 255, 0.3)',
          light: 'rgba(255, 255, 255, 0.1)',
          lighter: 'rgba(255, 255, 255, 0.05)',
          dark: 'rgba(0, 0, 0, 0.2)',
          darker: 'rgba(0, 0, 0, 0.3)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'system-ui', 'sans-serif'],
        mono: ['Roboto Mono', 'SF Mono', 'monospace'],
        display: ['Inter', 'SF Pro Display', 'sans-serif'],
      },
      backdropBlur: {
        xs: '2px',
      },
      boxShadow: {
        'glass': '0 8px 32px 0 rgba(31, 38, 135, 0.07)',
        'glass-lg': '0 8px 32px 0 rgba(31, 38, 135, 0.15)',
        'glow-cyan': '0 0 20px rgba(6, 182, 212, 0.3)',
        'glow-violet': '0 0 20px rgba(139, 92, 246, 0.3)',
      },
      animation: {
        'float': 'float 6s ease-in-out infinite',
        'float-slow': 'float 8s ease-in-out infinite',
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        'slide-up': 'slide-up 0.5s ease-out',
        'slide-down': 'slide-down 0.5s ease-out',
        'fade-in': 'fade-in 0.3s ease-in',
        'shimmer': 'shimmer 2s infinite',
        'blob': 'blob 7s infinite',
        // Landing page premium animations
        'aurora': 'aurora 12s ease infinite',
        'aurora-orb-1': 'aurora-orb-1 8s ease-in-out infinite',
        'aurora-orb-2': 'aurora-orb-2 10s ease-in-out infinite',
        'aurora-orb-3': 'aurora-orb-3 12s ease-in-out infinite',
        'shimmer-sweep': 'shimmer-sweep 2.5s linear infinite',
        'border-beam-spin': 'border-beam-spin var(--border-beam-duration, 12s) linear infinite',
        'meteor': 'meteor 8s linear infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-20px)' },
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'slide-up': {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'slide-down': {
          '0%': { transform: 'translateY(-100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'shimmer': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        blob: {
          '0%': { transform: 'translate(0px, 0px) scale(1)' },
          '33%': { transform: 'translate(30px, -50px) scale(1.1)' },
          '66%': { transform: 'translate(-20px, 20px) scale(0.9)' },
          '100%': { transform: 'translate(0px, 0px) scale(1)' },
        },
        // Premium landing page keyframes
        aurora: {
          '0%': { backgroundPosition: '50% 50%, 50% 50%' },
          '50%': { backgroundPosition: '350% 50%, 350% 50%' },
          '100%': { backgroundPosition: '50% 50%, 50% 50%' },
        },
        'aurora-orb-1': {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)', opacity: '0.3' },
          '33%': { transform: 'translate(60px, -40px) scale(1.2)', opacity: '0.5' },
          '66%': { transform: 'translate(-30px, 30px) scale(0.9)', opacity: '0.2' },
        },
        'aurora-orb-2': {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)', opacity: '0.25' },
          '50%': { transform: 'translate(-50px, 50px) scale(1.15)', opacity: '0.4' },
        },
        'aurora-orb-3': {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)', opacity: '0.2' },
          '40%': { transform: 'translate(40px, 20px) scale(1.1)', opacity: '0.35' },
          '70%': { transform: 'translate(-20px, -30px) scale(0.95)', opacity: '0.15' },
        },
        'shimmer-sweep': {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        'border-beam-spin': {
          '0%': { '--border-beam-angle': '0' },
          '100%': { '--border-beam-angle': '360' },
        },
        meteor: {
          '0%': { transform: 'rotate(215deg) translateX(0)', opacity: '1' },
          '70%': { opacity: '1' },
          '100%': { transform: 'rotate(215deg) translateX(-500px)', opacity: '0' },
        },
      },
    },
  },
  plugins: [],
  future: {
    hoverOnlyWhenSupported: true,
  },
}