import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { importTs } from './support/importTs.mjs'

const provider = await importTs('src/components/wallet/provider.ts')
const menu = await readFile(new URL('../src/components/wallet/WalletConnectMenu.tsx', import.meta.url), 'utf8')
const settings = await readFile(new URL('../src/pages/Settings.tsx', import.meta.url), 'utf8')
const sidebar = await readFile(new URL('../src/components/layout/Sidebar.tsx', import.meta.url), 'utf8')

function fakeWindow(values = {}) {
  const target = new EventTarget()
  return Object.assign(target, { setTimeout, ...values })
}

test('Phantom discovery checks its documented provider and a multi-wallet provider array', async () => {
  const direct = { isPhantom: true, request: async () => [] }
  const previous = globalThis.window
  try {
    globalThis.window = fakeWindow({ phantom: { ethereum: direct } })
    assert.equal((await provider.detectPhantom(0)).wallet?.provider, direct)

    const phantomInArray = { isPhantom: true, request: async () => [] }
    globalThis.window = fakeWindow({ ethereum: { request: async () => [], providers: [{ request: async () => [] }, phantomInArray] } })
    assert.equal((await provider.detectPhantom(0)).wallet?.provider, phantomInArray)
  } finally {
    globalThis.window = previous
  }
})

test('Phantom connection requests only the public EVM account', async () => {
  let method = ''
  const address = '0x1111111111111111111111111111111111111111'
  const result = await provider.requestPublicAddress({
    connector: 'phantom', name: 'Phantom',
    provider: { request: async (request) => { method = request.method; return [address] } },
  })
  assert.equal(method, 'eth_requestAccounts')
  assert.equal(result, address)
})

test('the header sheet is Phantom-only and routes secondary controls to Settings', () => {
  assert.match(menu, />Connect Phantom</)
  assert.match(menu, /More wallet options in Settings/)
  assert.doesNotMatch(menu, /<WalletPairing/)
  assert.doesNotMatch(menu, /Watch an account/)
  assert.doesNotMatch(menu, /Public WalletConnect project ID/)
})

test('Settings is visible and owns phone pairing and wallet management', () => {
  assert.match(sidebar, /to: '\/settings'/)
  assert.match(settings, /id="wallets"/)
  assert.match(settings, /<WalletConnections/)
})
