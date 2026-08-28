import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react({
    // Include .js files with JSX
    include: '**/*.{jsx,js,ts,tsx}',
  })],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    extensions: ['.js', '.jsx', '.json', '.ts', '.tsx'],  // Allow importing without file extensions
  },
  server: {
    port: 3000,
    open: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.js'],
    exclude: ['**/node_modules/**', './e2e/**'],
  },
  build: {
    outDir: 'build',
    sourcemap: false, // Disable sourcemaps for production to reduce build size
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          utils: ['axios', 'react-markdown', 'framer-motion']
        }
      }
    }
  },
});
