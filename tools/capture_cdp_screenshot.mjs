import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'

const require = createRequire(import.meta.url)
const WebSocket = require('../services/cockpit-ui/node_modules/ws')

const [endpoint = 'http://127.0.0.1:9227', url, output] = process.argv.slice(2)
if (!url || !output) throw new Error('usage: node tools/capture_cdp_screenshot.mjs <endpoint> <url> <output>')

const targets = await fetch(`${endpoint}/json/list`).then((response) => response.json())
const target = targets.find((item) => item.type === 'page')
if (!target?.webSocketDebuggerUrl) throw new Error('No debuggable page target is available')

const socket = new WebSocket(target.webSocketDebuggerUrl)
const pending = new Map()
let nextId = 1

await new Promise((resolve, reject) => {
  socket.once('open', resolve)
  socket.once('error', reject)
})

socket.on('message', (raw) => {
  const message = JSON.parse(raw.toString())
  if (!message.id) return
  const entry = pending.get(message.id)
  if (!entry) return
  pending.delete(message.id)
  if (message.error) entry.reject(new Error(message.error.message))
  else entry.resolve(message.result)
})

function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject })
    socket.send(JSON.stringify({ id, method, params }))
  })
}

await command('Page.enable')
await command('Network.enable')
await command('Emulation.setDeviceMetricsOverride', {
  width: 390,
  height: 844,
  deviceScaleFactor: 1,
  mobile: true,
  screenWidth: 390,
  screenHeight: 844,
})
await command('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 })
await command('Network.setUserAgentOverride', {
  userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36',
  platform: 'Android',
})
await command('Page.navigate', { url })
await new Promise((resolve) => setTimeout(resolve, 12000))
const metrics = await command('Runtime.evaluate', {
  expression: '({innerWidth, innerHeight, scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth})',
  returnByValue: true,
})
const capture = await command('Page.captureScreenshot', { format: 'png', fromSurface: true })
await writeFile(output, Buffer.from(capture.data, 'base64'))
console.log(JSON.stringify(metrics.result.value))
socket.close()
