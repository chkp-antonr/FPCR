import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export default defineConfig({
  root: __dirname,
  plugins: [react()],
  base: '/',
  server: {
    port: 5173,
    fs: {
      // Allow serving files from one level up to the project root
      allow: ['..']
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: resolve(__dirname, 'dist'),
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) => {
          if (assetInfo.name === 'favicon.ico') return 'favicon.ico';
          return 'assets/[name]-[hash][extname]';
        },
        manualChunks: (id) => {
          if (id.includes('node_modules')) {
            return 'vendor';
          }
        }
      }
    }
  }
});
