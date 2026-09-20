const { chromium } = require('E:/Projects/TradeSync/qa-runtime/node_modules/playwright-core')
const fs = require('node:fs/promises')
const path = require('node:path')

const output = process.env.TRADESYNC_QA_DIR
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set project-specific TRADESYNC_QA_DIR')

;(async () => {
  await fs.mkdir(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true })
  const results = []
  try {
    for (const viewport of [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport })
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await page.goto('http://127.0.0.1:3000/thesis', { waitUntil: 'networkidle', timeout: 90_000 })
      const player = page.getByRole('heading', { name: 'Interactive thesis playback', exact: true }).locator('xpath=ancestor::section')
      await player.waitFor({ timeout: 90_000 })
      await player.scrollIntoViewIfNeeded()
      await player.screenshot({ path: path.join(output, `interactive-thesis-${viewport.name}.png`) })

      const timeframes = await player.getByRole('button', { name: /^(1d|8h|4h|1h)$/ }).allTextContents()
      const audioSrc = await player.locator('audio').getAttribute('src')
      await player.getByRole('button', { name: '8h', exact: true }).click()
      await player.getByText(/8h · HYPERLIQUID/).waitFor({ timeout: 30_000 })
      await player.locator('canvas').first().waitFor({ state: 'visible', timeout: 30_000 })
      await player.screenshot({ path: path.join(output, `interactive-thesis-8h-${viewport.name}.png`) })

      const eth = player.getByRole('button', { name: 'ETH', exact: true })
      if (await eth.count()) {
        await eth.click()
        await player.getByText('ETH / USD', { exact: true }).waitFor({ timeout: 30_000 })
      }
      await player.getByRole('button', { name: 'Play', exact: true }).click()
      await page.waitForTimeout(1400)
      const audioTime = await player.locator('audio').evaluate((audio) => audio.currentTime)
      await player.getByRole('button', { name: 'Pause', exact: true }).click()
      const overflow = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        overflowing: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      }))
      results.push({ viewport, timeframes, audioSrc, audioTime, overflow, errors })
      await page.close()
    }
    await fs.writeFile(path.join(output, 'qa-results.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify(results, null, 2))
    if (results.some((result) => result.timeframes.length !== 4 || !result.audioSrc || result.audioTime <= 0 || result.overflow.overflowing || result.errors.length)) process.exitCode = 1
  } finally {
    await browser.close()
  }
})().catch((error) => { console.error(error); process.exitCode = 1 })
