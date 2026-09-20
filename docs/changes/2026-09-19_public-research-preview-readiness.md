# Public research-preview readiness — 19 September 2026

## Decision

TradeSync is prepared locally as a **source-available research preview** under
FSL-1.1-MIT. It must not be described as OSI open source. First-party source
and documentation use that licence; provider data, private integrations,
credentials, trademarks and third-party packages retain their own terms.

The existing public repository history is not asserted to be sanitized.
Removed captured-data and operator-specific files can remain reachable through
older Git objects even when the current working tree is clean. The safe release
candidate is therefore a history-free export; no force push, remote creation,
visibility change or publication was performed in this pass.

## Implemented release controls

- Added `LICENSE.md` using FSL-1.1-MIT.
- Added `PUBLIC_SOURCE_NOTICE.md`, `THIRD_PARTY_NOTICES.md` and `SECURITY.md`.
- Added a bring-your-own-credentials guide. Every downstream operator must
  create their own provider access and secrets; no account or key is supplied.
- Excluded captured replay data, derived real-data reports, private ChaseOS
  artifacts, Hermes prompts/outputs, credentials and operator-specific paths.
- Added `tools/public_release_audit.py` for current-tree or exported-tree
  checks. It prints file names and line numbers, never matched secret values.
- Added `tools/export_public_preview.py` to produce an audited current-tree
  package without `.git` history. It refuses to overwrite a non-empty
  destination and writes a SHA-256 file manifest.

## Verified candidate

History-free export:

`E:\Projects\TradeSync\public-research-preview-2026-09-19-r3`

The export contains the audited source set plus
`PUBLIC_EXPORT_MANIFEST.json`. The manifest records the exact file count, source commit, dirty
working-tree state, `history_included=false`, licence identifier and a SHA-256
digest for every copied file.

Verification results:

- source public-release audit: zero findings;
- exported-tree audit including the manifest: zero findings;
- root integration tests: 53 passed;
- State API Integration Pipeline and StrikeZone tests: 18 passed;
- Cockpit Hermes-control wording tests: 5 passed;
- Cockpit production build: passed, 3,200 modules transformed;
- Python compile check for audit/export/StrikeZone bridge: passed;
- `git diff --check`: passed; line-ending conversion notices remain warnings.

These checks establish the current-tree hygiene and tested architecture. They
do not prove that historical Git objects are clean, that provider terms will
never change, or that the system is profitable, continuously available or safe
for live execution.

## Public proof and video state

- The ChaseInTech TradeSync case study is prepared in
  `E:\Projects\ChaseInTech\2026-09-19-tradesync-public-proof`.
- Its production build passed: 119 pages, 122-page generated-link audit and
  Pagefind indexing. The focused final browser checks passed 2/2 at desktop and
  320 px.
- The page uses only Mission Control and Integration Pipeline captures. The
  Hermes image containing an internal hostname is quarantined outside the
  public worktree.
- The page deliberately withholds a GitHub link until a clean-history remote
  release is approved and verified.
- An editable 55-second CapCut draft and silent 9:16 proxy are prepared under
  `E:\Projects\TradeSync\2026-09-19-architecture-video`. Final operator
  voiceover, audio QA and publication remain pending.

## Publication order

1. Review this change and the history-free export.
2. Obtain explicit approval for the exact Git commit and remote strategy.
3. Create or select a clean-history public repository and push the approved
   export; do not force-rewrite the existing public history without a separate
   migration decision.
4. Read back the public repository and enable the source link in ChaseInTech.
5. Commit, push and deploy the ChaseInTech page under separate approval, then
   verify the canonical URL.
6. Add final voiceover/audio, re-run media QA, and only then publish the
   architecture-first LinkedIn/X campaign after explicit approval.
