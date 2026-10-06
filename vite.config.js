import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  build: {
    assetsInlineLimit: 0,
    rollupOptions: { input: { index: 'index.html', review: 'review.html' } },
  },
});
