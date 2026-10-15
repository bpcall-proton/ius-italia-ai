import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; " +
  "connect-src 'self' http://127.0.0.1:* http://localhost:*; frame-src blob:; object-src blob:; base-uri 'none'; form-action 'none'"

export default defineConfig({
  base: './',
  plugins: [
    react(),
    {
      name: 'ius-csp',
      apply: 'build',
      transformIndexHtml: (html) =>
        html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`),
    },
  ],
})
