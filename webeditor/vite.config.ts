import { defineConfig } from 'vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// Jeden soubor bez externích odkazů: hostitel (QtWebEngine / Android WebView) ho
// načte z disku nebo z assets, žádný server ani síť. Výstup jde rovnou do
// desktopové aplikace (app/webeditor/index.html); Android si ho kopíruje do assets.
export default defineConfig({
  plugins: [viteSingleFile()],
  base: './',
  build: {
    outDir: '../app/webeditor',
    emptyOutDir: true,
    target: 'es2020',
    cssCodeSplit: false,
    assetsInlineLimit: 100_000_000,
    reportCompressedSize: false,
  },
})
