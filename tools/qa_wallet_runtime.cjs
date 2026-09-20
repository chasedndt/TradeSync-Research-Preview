const { chromium } = require('E:/Projects/TradeSync/qa-runtime/node_modules/playwright-core');
const fs = require('node:fs/promises');
const path = require('node:path');

const output = process.env.TRADESYNC_QA_DIR;
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set project-specific TRADESYNC_QA_DIR');

async function overflow(page) {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const elements = [...document.querySelectorAll('body *')].map((element) => {
      const rect = element.getBoundingClientRect();
      return { tag: element.tagName, className: String(element.className || '').slice(0, 120), text: String(element.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80), left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width) };
    }).filter((item) => item.right > width + 1 && item.left < width).slice(0, 20);
    return { clientWidth: width, scrollWidth: document.documentElement.scrollWidth, overflowing: document.documentElement.scrollWidth > width + 1, elements };
  });
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const viewport of [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport });
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));

      await page.goto('http://127.0.0.1:3000/execution', { waitUntil: 'domcontentloaded' });
      const wallet = page.getByRole('heading', { name: 'Watch-only account', exact: true }).locator('xpath=ancestor::section[1]');
      await wallet.waitFor({ timeout: 30_000 });
      await page.screenshot({ path: path.join(output, `execution-full-${viewport.name}.png`), fullPage: true });
      await wallet.screenshot({ path: path.join(output, `wallet-${viewport.name}.png`) });
      const executionOverflow = await overflow(page);

      await page.goto('http://127.0.0.1:3000/market', { waitUntil: 'domcontentloaded' });
      const heatmap = page.getByRole('heading', { name: 'Resting liquidity heatmap', exact: true }).locator('xpath=ancestor::section[1]');
      await heatmap.waitFor({ timeout: 90_000 });
      await heatmap.getByRole('button', { name: '4d', exact: true }).click();
      await page.waitForTimeout(3_000);
      await page.screenshot({ path: path.join(output, `market-full-${viewport.name}.png`), fullPage: true });
      await heatmap.screenshot({ path: path.join(output, `liquidity-4d-${viewport.name}.png`) });
      const marketOverflow = await overflow(page);

      results.push({ viewport, executionOverflow, marketOverflow, errors });
      await page.close();
    }
    await fs.writeFile(path.join(output, 'qa-results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
