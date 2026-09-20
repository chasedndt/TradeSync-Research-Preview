# Comprehensive market briefing and wallet routes — 17 September 2026

## Repo-truth delta

The Market Thesis player could change a real Hyperliquid chart, but its spoken
story still behaved like a rapid symbol carousel and the surrounding page did
not provide the month-to-intraday context needed to understand the market.
Risk/reward geometry used price values but did not continuously re-project
itself while the chart axes moved. The header wallet entry also over-emphasised
the Hyperliquid account label and made an injected Phantom extension look like
the only usable route, which is unsuitable for guest/incognito and future
standalone-app sessions.

## Implemented

- The Thesis page now puts a measured, sectioned briefing before any trade
  illustration: market breadth, BTC month/week/day/intraday structure, ETH and
  relative strength, altcoin breadth, scheduled macro risk, news/on-chain
  context, scenarios and a data-coverage ledger.
- BTC and ETH show `1m`, `2w`, `1w`, `3d`, `1d`, `8h`, `4h` and `1h` horizon
  reads. Trend wording, momentum, measured ranges, RSI evidence and ETH-versus-
  BTC relative momentum are stated in plain language.
- New thesis editions freeze the BTC/ETH horizon context used during assembly
  and produce six integrated narration chapters: overview, Bitcoin, Ethereum,
  altcoin breadth, macro risk and scenario workshop.
- The existing ChaseOS-compatible configured voice renders one synchronized
  audio track, subtitles and MP4 fallback. The interactive player uses the same
  six subtitle cues, keeps captions on the chart, and waits until the final
  scenario chapter before showing any paper position geometry.
- Playback changes one chart state per spoken chapter instead of cycling seven
  timeframes inside every sentence. Operators can still inspect any supported
  timeframe manually.
- The scenario overlay continuously derives X and Y coordinates from the chart
  time and price scales. It therefore remains attached during timeframe,
  resize, zoom and axis changes. Stop, entry and target labels fan outward when
  real prices are too close to label without overlap.
- The player has a browser Theater/fullscreen control and remains a display-
  only surface: it creates no signal, drawing, approval or order.
- The header now uses a larger Phantom mark with a concise `Connect wallet`
  control at the far right. Local workstation controls have a separate compact
  visual treatment.
- The wallet chooser exposes three explicit routes: injected browser wallet,
  short-lived WalletConnect QR/mobile pairing, and watch-only public address.
  It explains guest/incognito constraints and never presents a seed-phrase or
  private-key input.

## Honest data boundary

The briefing uses data TradeSync can currently measure: Hyperliquid candles,
volume, funding/open-interest context, horizon trend/momentum/ranges, frozen
edition breadth, scheduled events, retained macro/news headlines, measured
event reactions and available context providers.

Total crypto market cap, BTC dominance, Fear & Greed, authoritative ETF flows
and a native ETH/BTC candle history are not yet part of the briefing contract.
A true naked POC/VAH/VAL also remains unavailable: candle volume does not prove
where volume traded inside the candle, so TradeSync must retain trade-at-price
bins before presenting a volume profile as authoritative.

## Runtime acceptance

- Generated edition `a20f4ab0-41f7-47e2-bd01-da83ea9814dd` with frozen BTC and
  ETH horizon context and six narration chapters.
- Rendered `narration.mp3`, `edition.srt` and `edition.mp4` with the existing
  voice pipeline; the browser loaded a 2:49 synchronized track and six chapters.
- Desktop rendered acceptance showed live eight-horizon BTC/ETH evidence,
  seven long and one short altcoin read, live news/context and final-chapter-only
  risk geometry.
- Switching the final scenario from `1h` to `4h` re-projected entry, target and
  stop coordinates while retaining the same stored price values.
- A 390 x 844 touch viewport had no horizontal page overflow. The wallet sheet
  retained the large Phantom state, QR/mobile explanation and safety boundary.
- Canonical visual evidence: `E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-17-comprehensive-thesis-wallet`.

## Verification

- `npm test` — 255 passed.
- `npx tsc --noEmit` — passed.
- `python -m pytest tests/test_market_outlook.py services/state-api/tests/test_editions_schedule.py -q` with the repo `PYTHONPATH` — 10 passed.
- `python -m py_compile services/state-api/app/editions.py libs/tradesync_core/tradesync_core/outlook_render.py tools/thesis_video.py` — passed.
- `npm run build` — passed.
- Docker rebuilt and recreated `state-api` and `cockpit-ui`; `/healthz` returned `ok: true` and `/state/health` returned healthy with PostgreSQL answering.

## Untouched boundaries and remaining operator acceptance

- TradeSync does not collect a recovery phrase or master private key. Signing,
  agent-wallet approval and live execution remain separate fail-closed gates.
- WalletConnect QR/mobile code is present, but a physical pairing cannot occur
  until the operator supplies a public Reown project ID. No secret is required.
- Phantom embedded accounts require a Phantom Portal App ID and provider/domain
  configuration; they were not silently substituted for the user's existing
  wallet.
- Browser Theater mode and real speaker output still require operator-visible
  acceptance in the launched profile; automated browser control cannot prove
  audio hardware output.
- Execution remains disabled. The briefing and paper geometry do not establish
  a profitable strategy; registered forward evidence after costs remains the
  promotion gate.
