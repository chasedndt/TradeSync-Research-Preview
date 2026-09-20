import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

// TradeSync is watch-only, with address-only WalletConnect pairing. No field anywhere in the Cockpit may ask
// for a recovery phrase, a private or secret key, or a wallet passphrase.
const SRC = fileURLToPath(new URL('../src/', import.meta.url))
const FORBIDDEN = /seed|mnemonic|recovery phrase|private key|secret key|passphrase/i
const FIELDS = new Set(['input', 'textarea'])

async function sourceFiles(dir) {
  const files = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...(await sourceFiles(path)))
    else if (entry.name.endsWith('.tsx')) files.push(path)
  }
  return files
}

function strings(node, source) {
  const found = []
  const visit = (child) => {
    if (ts.isStringLiteral(child) || ts.isNoSubstitutionTemplateLiteral(child)) found.push(child.text)
    else if (ts.isTemplateExpression(child)) found.push(child.head.text, ...child.templateSpans.map((span) => span.literal.text))
    else if (ts.isJsxText(child)) found.push(child.getText(source))
    ts.forEachChild(child, visit)
  }
  visit(node)
  return found
}

/** Every text a field shows or is named by: its attributes and the text of a label around it. */
export function fieldTexts(fileName, text) {
  const source = ts.createSourceFile(fileName, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const fields = []
  const visit = (node) => {
    if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && FIELDS.has(node.tagName.getText(source))) {
      const texts = strings(node.attributes, source)
      for (let parent = node.parent; parent; parent = parent.parent) {
        if (ts.isJsxElement(parent) && parent.openingElement.tagName.getText(source) === 'label') {
          texts.push(...parent.children.filter((child) => ts.isJsxText(child)).map((child) => child.getText(source)))
          break
        }
      }
      const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1
      fields.push({ line, text: texts.join(' ').replace(/\s+/g, ' ').trim() })
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
  return fields
}

test('the scanner reads each field attributes, including conditional ones, and the label around it', () => {
  const sample = [
    'export const A = ({ x }) => <form>',
    "  <label>Recovery phrase<input placeholder={x ? 'Seed words' : 'Other'} /></label>",
    '  <textarea aria-label="Private key" />',
    '  <input value={x} />',
    '</form>',
  ].join('\n')
  const texts = fieldTexts('sample.tsx', sample).map((field) => field.text)
  assert.equal(texts.length, 3)
  assert.match(texts[0], /Seed words/)
  assert.match(texts[0], /Recovery phrase/)
  assert.match(texts[1], /Private key/)
})

test('no Cockpit field asks for a seed phrase, a private or secret key, or a passphrase', async () => {
  const offences = []
  let fields = 0
  for (const file of await sourceFiles(SRC)) {
    for (const field of fieldTexts(file, await readFile(file, 'utf8'))) {
      fields += 1
      if (FORBIDDEN.test(field.text)) offences.push(`${relative(SRC, file)}:${field.line}: ${field.text.slice(0, 120)}`)
    }
  }
  assert.ok(fields >= 20, `the scanner found only ${fields} fields`)
  assert.deepEqual(offences, [])
})
