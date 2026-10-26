import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true },
  build: {
    // ECharts alone is ~1 MB minified; keep it (and Leaflet) in their own cacheable chunks.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: { manualChunks: { echarts: ['echarts', 'echarts-for-react'], map: ['leaflet', 'react-leaflet'] } },
    },
  },
});
