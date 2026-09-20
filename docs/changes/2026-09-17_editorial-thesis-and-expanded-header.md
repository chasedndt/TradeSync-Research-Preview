# Editorial thesis and expanded-sidebar header — 17 September 2026

## Repo-truth delta

The prior Mission Control revision exposed more evidence but presented it as a
large scorecard, asset table and timeframe matrix. That was technically fuller
and practically worse: the operator still had to translate terse labels and raw
relative percentages into a market story. On the Thesis page the same evidence
block also appeared before the interactive chart. Header acceptance had been
performed with the sidebar collapsed, so it did not prove the layout the
operator actually uses.

## Implemented

- One deterministic narrative builder now turns retained BTC/ETH horizon data,
  measured support/resistance and the frozen event calendar into ordinary
  paragraphs about the month, week and next session.
- Mission Control begins with that editorial Bitcoin explanation, a small
  support/current/resistance picture, links to the live chart and narrated
  thesis, and three conditional paragraphs for confirmation, waiting and
  invalidation. The four-card scorecard, duplicated asset tables and jargon-led
  matrix were removed from the primary thesis.
- The Thesis page places Interactive Thesis Playback immediately after the
  edition selector. Its written thesis follows as a readable three-part article
  with a real 120-candle Bitcoin daily chart, source links and plain-English
  scenarios.
- Raw BTC/ETH timeframe states and coverage limitations remain inspectable in a
  closed `Evidence behind this thesis` disclosure. They no longer interrupt the
  reading flow.
- The stored six-chapter narration now uses the same editorial order. It speaks
  the month and week, Bitcoin's support/resistance decision area, ETH and
  altcoin context, scheduled catalysts and evidence limits before the final
  scenario. It no longer recites raw relative percentages or `regime` jargon.
- A fresh edition (`5c427f08-3282-4131-86e3-3973c4df73bc`) was generated and
  rendered into a 3:30 ChaseOS-compatible voice track, synchronized captions
  and MP4 fallback, so the running player does not retain the rejected script.
- With the desktop sidebar expanded, the Phantom connector becomes a prominent
  official-icon action, Controls becomes icon-only, the harness label compacts
  and optional pipeline detail is hidden. The header retains accessible names
  and the full wallet dialog.
- At 390 px the header keeps the official Phantom action fully visible. The
  direct harness Start/Stop button moves to the Hermes & agents page at this
  width while its state link remains in the header.

## Verification

- `npm test`: 261 passed.
- `npm run build`: passed.
- Docker image rebuilt and `cockpit-ui` recreated in the canonical
  `tradesync-full` runtime.
- Browser acceptance was performed at 1368 x 900 with the sidebar explicitly
  expanded, then at mobile width. Mission Control had no horizontal overflow;
  the Phantom icon, Controls, pipeline and harness actions remained inside the
  header. The Thesis page showed the interactive player before the editorial
  article.
- The regenerated edition loaded six new caption cues and a 210-second audio
  duration. The first cue begins with the larger picture and the final cue is
  the first one to introduce position geometry.
- `python -m pytest tests/test_market_outlook.py services/state-api/tests/test_editions_schedule.py -q`: 10 passed.

## Boundaries

The prose and narration explain retained measurements; they do not manufacture missing ETF,
dominance, sentiment or volume-at-price evidence. YouTube creators from the
operator-approved Strike Zone allowlist were inspected as presentation context,
not promoted as market authority. Execution remains disabled and the wallet
action requests only a public address.

## Visual QA

`E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-17-editorial-thesis-expanded-sidebar\QA.md`
