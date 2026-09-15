import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Split the heavy third-party libraries out of the app chunk. Recharts in
        // particular is only used on the two researcher screens, so it should not be
        // part of what a student downloads to reach the workspace.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          editor: ['@monaco-editor/react'],
        },
      },
    },
  },
  server: {
    port: 3000,
    open: true,
    // Bind IPv4 explicitly: left to itself Vite listens on [::1] only, so
    // http://127.0.0.1:3000 refuses the connection and the browser shows
    // "can't reach this page" whenever it resolves localhost to IPv4.
    // Use host: true instead to also serve the LAN (classroom sessions).
    host: '127.0.0.1',
    proxy: {
      // 127.0.0.1, not localhost: Node resolves localhost to ::1 first, but
      // `runserver 8000` binds IPv4, so a localhost target makes every
      // /api call fail with ECONNREFUSED while both servers look healthy.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      '/media': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
