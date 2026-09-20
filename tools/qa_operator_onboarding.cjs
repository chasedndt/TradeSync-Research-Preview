// The operator onboarding panels at desktop and phone widths, against a Vite dev server whose /api reads from the
// running state-api and cannot change it (services/cockpit-ui/vite.qa-readonly.config.mjs).
//
// Reads only. Every /api request other than GET or HEAD is aborted in the browser and recorded as a violation, and
// the dev server refuses them too. The routes this branch adds are not deployed, so they are answered from fixtures
// marked QA FIXTURE: the WalletConnect settings, and the TradingView setup, whose contract facts come from
// tradesync_core and whose receipts come from the live GET /state/quarantine?source=tradingview. One pass answers
// the mobile routes from a fixture of two enrolled phones so the checklist marks can be seen; nothing is enrolled
// or sent.
//
// Usage: set TRADESYNC_QA_DIR to a folder under "TradeSync Visual QA", TRADESYNC_QA_BASE to the dev server
// (default http://127.0.0.1:5199) and TRADESYNC_QA_PYTHON to the project venv's python, then
//   node tools/qa_operator_onboarding.cjs
const { chromium, request: playwrightRequest } = require('playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const output = process.env.TRADESYNC_QA_DIR;
if (!output || !output.includes('TradeSync Visual QA')) throw new Error('Set TRADESYNC_QA_DIR to a folder under TradeSync Visual QA');
const base = process.env.TRADESYNC_QA_BASE || 'http://127.0.0.1:5199';
if (/:(3000|8000)\b/.test(base)) throw new Error('Point TRADESYNC_QA_BASE at the read-only dev server, not the deployed Cockpit or state-api');
const python = process.env.TRADESYNC_QA_PYTHON || 'python';
const READS = new Set(['GET', 'HEAD']);
const WIDTHS = [1366, 375];
const FIXTURE_ID = '0123456789abcdef0123456789abcdef';

const SCENARIOS = [
  { name: 'settings', route: '/settings', regions: ['Mobile notifications', 'Operator access', 'WalletConnect project ID', 'TradingView alerts'], open: ['Turn it on'] },
  { name: 'settings-phones-fixture', route: '/settings', phones: true, regions: ['Mobile notifications'] },
  { name: 'intake', route: '/intake', regions: ['TradingView alerts'], open: ['How to set up an alert'] },
  { name: 'intake-no-secret-fixture', route: '/intake', secretConfigured: false, regions: ['TradingView alerts'] },
  { name: 'execution', route: '/execution', panels: ['Watch-only account'] },
];

const MOBILE_STATUS = { configured: true, worker_running: true, note: 'QA FIXTURE: nothing is enrolled on the running stack and nothing is sent.' };
const MOBILE_DEVICES = {
  devices: [
    { id: 'qa-android', label: 'QA FIXTURE Android', platform: 'android', enabled: true, operator_confirmed_at: '2026-09-15T19:00:00+00:00',
      notification_preferences: { paper_events: false, control_events: true, timezone: 'Europe/London', quiet_enabled: true, quiet_start: 22, quiet_end: 8, daily_budget: 10 } },
    { id: 'qa-iphone', label: 'QA FIXTURE iPhone', platform: 'ios', enabled: true, operator_confirmed_at: null, notification_preferences: {} },
  ],
  events: [
    { id: 'qa000001-android-test', device_id: 'qa-android', kind: 'test', status: 'operator_confirmed', attempts: 1, created_at: '2026-09-15T18:59:00+00:00', last_error: null },
    { id: 'qa000002-iphone-test', device_id: 'qa-iphone', kind: 'test', status: 'provider_accepted', attempts: 1, created_at: '2026-09-15T19:05:00+00:00', last_error: null },
  ],
};
const WALLETCONNECT = {
  schema_version: 'walletconnect_settings_v1', project_id: FIXTURE_ID, updated_by: 'QA FIXTURE', updated_at: '2026-09-15T20:00:00+00:00',
  changes: [{ changed_by: 'QA FIXTURE', changed_at: '2026-09-15T20:00:00+00:00', previous: null, next: FIXTURE_ID }],
  project_site: 'https://dashboard.reown.com', public: true, note: 'QA FIXTURE',
};

// Runs in the page: elements reaching past the viewport that no scrolling container holds (from qa_all_pages.cjs).
function overflowProbe() {
  const limit = window.innerWidth + 1;
  const contained = (el) => {
    for (let node = el.parentElement; node && node !== document.body; node = node.parentElement) {
      if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(node).overflowX)) return true;
    }
    return false;
  };
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.right <= limit || contained(el)) continue;
    const cls = typeof el.className === 'string' && el.className ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}` : '';
    offenders.push(`${el.tagName.toLowerCase()}${cls} right=${Math.round(rect.right)}`);
    if (offenders.length >= 5) break;
  }
  return { documentWidth: document.documentElement.scrollWidth, viewport: window.innerWidth, offenders };
}

const slug = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

function contractFacts() {
  const code = 'import json; from tradesync_core import tradingview_webhook as w; print(json.dumps({"webhook_url": w.PUBLIC_WEBHOOK_URL, '
    + '"contract": w.SCHEMA_VERSION, "required_fields": list(w.REQUIRED_FIELDS), "secret_placeholder": w.SECRET_PLACEHOLDER, '
    + '"message_template": w.message_template()}))';
  const env = { ...process.env, PYTHONPATH: path.join(ROOT, 'libs', 'tradesync_core') };
  return JSON.parse(execFileSync(python, ['-c', code], { env }).toString());
}

async function liveReceipts() {
  const api = await playwrightRequest.newContext();
  try {
    const response = await api.get(`${base}/api/state/quarantine?source=tradingview&limit=5`);
    if (!response.ok()) return { receipts: [], note: `live quarantine read answered ${response.status()}` };
    const { items } = await response.json();
    const receipts = items.map((item) => ({
      id: item.id, received_at: item.received_at, accepted: item.accepted,
      indicator: String(item.payload?.indicator ?? ''), ticker: String(item.payload?.ticker ?? ''), interval: String(item.payload?.interval ?? ''),
      reasons: item.reasons ?? [], review: item.promoted_to ? 'promoted' : item.reviewed_by ? 'reviewed' : 'awaiting review',
    }));
    return { receipts, note: `${receipts.length} live TradingView receipts read` };
  } finally {
    await api.dispose();
  }
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  const facts = contractFacts();
  const live = await liveReceipts();
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const results = [];
  try {
    for (const width of WIDTHS) {
      for (const scenario of SCENARIOS) {
        const phone = width < 768;
        const context = await browser.newContext({ viewport: { width, height: 900 }, isMobile: phone, hasTouch: phone });
        const violations = [];
        const errors = [];
        const fixtures = new Set();
        await context.route((url) => url.pathname.startsWith('/api/'), (route) => {
          const request = route.request();
          if (READS.has(request.method())) return route.fallback();
          violations.push(`${request.method()} ${new URL(request.url()).pathname}`);
          return route.abort('blockedbyclient');
        });
        const fixture = (pathname, body) => context.route((url) => url.pathname === pathname, (route) => {
          if (!READS.has(route.request().method())) return route.fallback();
          fixtures.add(pathname);
          return route.fulfill({ json: body });
        });
        await fixture('/api/state/settings/walletconnect', WALLETCONNECT);
        await fixture('/api/state/tradingview/setup', {
          schema_version: 'tradingview_setup_v1', ...facts, secret_configured: scenario.secretConfigured ?? true, receipts: live.receipts,
          receipts_error: null, refusal_log_marker: 'tradingview alert refused', authority: 'none', note: 'QA FIXTURE',
        });
        if (scenario.phones) {
          await fixture('/api/state/mobile-alerts/status', MOBILE_STATUS);
          await fixture('/api/state/mobile-alerts/devices', MOBILE_DEVICES);
        }

        const page = await context.newPage();
        page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
        page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 200)}`); });
        await page.goto(base + scenario.route, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => !document.body.innerText.includes('Loading page…'), null, { timeout: 20000 })
          .catch(() => errors.push('page code did not load within 20 s'));
        await page.waitForTimeout(3500);
        for (const text of scenario.open ?? []) {
          const summary = page.locator('summary', { hasText: text }).first();
          if (await summary.count() && !(await summary.evaluate((node) => node.parentElement.open))) await summary.click();
        }
        await page.waitForTimeout(400);

        const layout = await page.evaluate(overflowProbe);
        const screenshots = [`${scenario.name}-${width}.png`];
        await page.screenshot({ path: path.join(output, screenshots[0]), fullPage: true });
        for (const name of scenario.regions ?? []) {
          const region = page.getByRole('region', { name, exact: true }).first();
          if (!(await region.count())) { errors.push(`region not found: ${name}`); continue; }
          const file = `${scenario.name}-${slug(name)}-${width}.png`;
          await region.screenshot({ path: path.join(output, file) });
          screenshots.push(file);
        }
        for (const heading of scenario.panels ?? []) {
          const panel = page.getByRole('heading', { name: heading, exact: true }).locator('xpath=ancestor::section[1]');
          if (!(await panel.count())) { errors.push(`panel not found: ${heading}`); continue; }
          const file = `${scenario.name}-${slug(heading)}-${width}.png`;
          await panel.screenshot({ path: path.join(output, file) });
          screenshots.push(file);
        }
        results.push({
          scenario: scenario.name, route: scenario.route, width, violations, errors, fixtures: [...fixtures],
          overflow: layout.documentWidth > layout.viewport + 1, ...layout, screenshots,
        });
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  await fs.writeFile(path.join(output, 'summary.json'), JSON.stringify({ base, liveReceipts: live.note, results }, null, 2));
  for (const r of results) {
    const findings = [
      r.violations.length && `${r.violations.length} non-GET requests blocked`, r.overflow && 'page overflows',
      r.offenders.length && `${r.offenders.length} wide elements`, r.errors.length && `${r.errors.length} errors`,
    ].filter(Boolean);
    console.log(`${r.width}px ${r.scenario}: ${findings.length ? findings.join(', ') : 'ok'}`);
  }
  const failing = results.filter((r) => r.violations.length || r.errors.length || r.overflow || r.offenders.length);
  console.log(`${live.note}; ${results.length} views, ${failing.length} with findings; summary.json in ${output}`);
  process.exitCode = failing.length ? 1 : 0;
})().catch((error) => { console.error(error); process.exitCode = 1; });
