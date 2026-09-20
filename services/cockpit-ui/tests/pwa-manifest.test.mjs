import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const root = (path) => fileURLToPath(new URL(`../${path}`, import.meta.url))
const manifest = JSON.parse(await readFile(root('public/manifest.webmanifest'), 'utf8'))
const indexHtml = await readFile(root('index.html'), 'utf8')
const indexCss = await readFile(root('src/index.css'), 'utf8')
const nginx = await readFile(root('nginx.conf'), 'utf8')

/** A PNG's real pixel size, read from its header, so the manifest cannot claim a size the file does not have. */
async function pngSize(path) {
  const header = (await readFile(path)).subarray(0, 24)
  assert.equal(header.subarray(0, 8).toString('hex'), '89504e470d0a1a0a', `${path} is not a PNG`)
  return { width: header.readUInt32BE(16), height: header.readUInt32BE(20) }
}

test('the manifest installs the Cockpit as a standalone app at the site root', () => {
  assert.equal(manifest.name, 'TradeSync Cockpit')
  assert.equal(manifest.short_name, 'TradeSync')
  assert.equal(manifest.display, 'standalone')
  assert.equal(manifest.scope, '/')
  assert.equal(manifest.start_url, '/')
})

test('the installed app is the colour of the Cockpit itself', () => {
  const canvas = /--canvas:\s*(#[0-9a-fA-F]{6})/.exec(indexCss)?.[1]
  assert.ok(canvas, 'index.css no longer defines --canvas')
  assert.equal(manifest.theme_color, canvas)
  assert.equal(manifest.background_color, canvas)
  assert.ok(indexHtml.includes(`<meta name="theme-color" content="${canvas}" />`))
})

test('every icon the manifest names exists at the size it claims, and one is maskable', async () => {
  assert.ok(manifest.icons.length >= 3)
  for (const icon of manifest.icons) {
    assert.ok(icon.src.startsWith('/brand/'), icon.src)
    const path = root(`public${icon.src}`)
    await stat(path)
    const [width, height] = icon.sizes.split('x').map(Number)
    assert.deepEqual(await pngSize(path), { width, height }, icon.src)
    assert.equal(icon.type, 'image/png')
  }
  const purposes = manifest.icons.map((icon) => icon.purpose)
  assert.ok(purposes.includes('maskable'))
  assert.ok(purposes.includes('any'))
})

test('the page links the manifest and tells an iPhone what to use', () => {
  assert.ok(indexHtml.includes('<link rel="manifest" href="/manifest.webmanifest" />'))
  assert.ok(indexHtml.includes('name="apple-mobile-web-app-capable" content="yes"'))
  assert.ok(indexHtml.includes('rel="apple-touch-icon"'))
})

test('the service worker sits at the site root so it can control every page', async () => {
  await stat(root('public/sw.js'))
  await stat(root('public/offline.html'))
})

/** One nginx exact-match location block, up to the next location, so a nested brace cannot fool the check. */
function locationBlock(path) {
  const start = nginx.indexOf(`location = ${path} {`)
  assert.notEqual(start, -1, `nginx.conf has no exact-match location for ${path}`)
  const rest = nginx.slice(start)
  const next = rest.indexOf('location ', 1)
  return next === -1 ? rest : rest.slice(0, next)
}

test('nginx never pins the service worker, the manifest or the offline page', () => {
  const worker = locationBlock('/sw.js')
  assert.match(worker, /Cache-Control "no-cache/)
  assert.match(worker, /Service-Worker-Allowed "\/"/)
  assert.match(locationBlock('/manifest.webmanifest'), /Cache-Control "no-cache/)
  assert.match(locationBlock('/manifest.webmanifest'), /application\/manifest\+json/)
  assert.match(locationBlock('/offline.html'), /Cache-Control "no-cache/)
  // The year-long immutable rule still exists for hashed build assets, and must not reach the worker.
  assert.match(nginx, /expires 1y/)
})
