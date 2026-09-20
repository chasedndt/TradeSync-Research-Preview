const { chromium } = require('E:/Projects/TradeSync/qa-runtime/node_modules/playwright-core')
const fs = require('node:fs/promises')
const path = require('node:path')

const output = process.env.TRADESYNC_QA_DIR
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set project-specific TRADESYNC_QA_DIR')

async function overflow(page) {
  return page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflowing: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  }))
}

;(async () => {
  await fs.mkdir(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true })
  const results = []
  try {
    for (const viewport of [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport })
      const errors = []
      const expectedUnavailable = []
      page.on('pageerror', (error) => errors.push(error.message))
      page.on('response', (response) => { if (response.status() >= 500) expectedUnavailable.push(`${response.status()} ${response.url()}`) })
      await page.goto('http://127.0.0.1:3000/', { waitUntil: 'networkidle', timeout: 90_000 })
      await page.getByRole('heading', { name: 'Market horizon map', exact: true }).waitFor({ timeout: 90_000 })
      await page.screenshot({ path: path.join(output, `mission-control-${viewport.name}.png`), fullPage: true })
      const homeOverflow = await overflow(page)

      await page.getByRole('button', { name: /Connect wallet|Wallets/ }).click()
      const walletDialog = page.getByRole('dialog', { name: 'Connect a wallet' })
      await walletDialog.waitFor()
      await walletDialog.screenshot({ path: path.join(output, `wallet-modal-${viewport.name}.png`) })
      const secretInputs = await walletDialog.locator('input').count()
      await page.getByRole('button', { name: 'Close wallet menu' }).click()

      await page.getByRole('button', { name: /Local workstation controls/ }).click()
      const operatorDialog = page.getByRole('dialog', { name: 'Operator' })
      await operatorDialog.waitFor()
      await operatorDialog.screenshot({ path: path.join(output, `operator-menu-${viewport.name}.png`) })
      const jsonLinks = await operatorDialog.getByText('JSON', { exact: true }).count()
      await page.getByRole('button', { name: 'Close local controls' }).click()

      await page.goto('http://127.0.0.1:3000/execution', { waitUntil: 'networkidle', timeout: 90_000 })
      await page.getByRole('heading', { name: 'Connected accounts', exact: true }).waitFor()
      await page.screenshot({ path: path.join(output, `execution-wallet-${viewport.name}.png`), fullPage: true })
      results.push({ viewport, homeOverflow, secretInputs, jsonLinks, errors, expectedUnavailable })
      await page.close()
    }
    await fs.writeFile(path.join(output, 'qa-results.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify(results, null, 2))
    if (results.some((r) => r.homeOverflow.overflowing || r.secretInputs !== 0 || r.jsonLinks !== 0 || r.errors.length)) process.exitCode = 1
  } finally {
    await browser.close()
  }
})().catch((error) => { console.error(error); process.exitCode = 1 })
