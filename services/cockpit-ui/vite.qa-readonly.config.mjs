// A Vite dev server for visual QA that reads from the running state-api and cannot change it.
//
// /api is proxied to TRADESYNC_QA_API_TARGET (default http://127.0.0.1:8000) for GET and HEAD only. Any other
// method is answered 404 by this server and never forwarded. tools/qa_operator_onboarding.cjs also aborts
// every non-GET request in the browser, so neither layer is relied on alone.
//
// Usage, from services/cockpit-ui:
//   npx vite --config vite.qa-readonly.config.mjs --port 5199 --strictPort --host 127.0.0.1
import { defineConfig, mergeConfig } from 'vite'
import base from './vite.config.ts'

const READS = new Set(['GET', 'HEAD'])
const target = process.env.TRADESYNC_QA_API_TARGET || 'http://127.0.0.1:8000'

export default mergeConfig(base, defineConfig({
  server: {
    proxy: {
      '/api': {
        target,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // Returning false makes Vite answer 404 itself, before anything is proxied.
        bypass: (request) => (READS.has(request.method ?? '') ? undefined : false),
      },
    },
  },
}))
