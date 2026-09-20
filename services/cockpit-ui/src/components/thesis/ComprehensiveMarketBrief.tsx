import { NavLink } from 'react-router-dom'
import type { MarketOutlook, ThesisEdition } from '../../api/types'
import { useCandles } from '../../api/hooks/useCandles'
import { useContextOverview } from '../../api/hooks/useContextOverview'
import { useHorizonPage } from '../../api/hooks/useHorizons'
import { useMacroHeadlines } from '../../api/hooks/useMacroFeed'
import { PriceChart } from '../canvas/PriceChart'
import { buildMarketNarrative, horizon, price } from './marketNarrative'
import styles from './ComprehensiveMarketBrief.module.css'

function compactEvidence(symbol: string, page: ReturnType<typeof useHorizonPage>['data']) {
  const windows = ['1m', '1w', '1d', '4h'] as const
  return <div className={styles.evidenceAsset}>
    <strong>{symbol}</strong>
    {windows.map((key) => {
      const item = horizon(page, key)
      return <span key={key}><b>{key}</b>{item?.available ? `${item.trend?.state.replace(/_/g, ' ') ?? 'trend unavailable'} · ${item.momentum?.state ?? 'momentum unavailable'}` : 'not measured'}</span>
    })}
  </div>
}

/** An editorial thesis first; raw measurements remain available as an optional appendix. */
export function ComprehensiveMarketBrief({ edition, outlook }: { edition: ThesisEdition; outlook: MarketOutlook }) {
  const btc = useHorizonPage('BTC-PERP')
  const eth = useHorizonPage('ETH-PERP')
  const candles = useCandles('BTC-PERP', '1d', 120)
  const context = useContextOverview()
  const news = useMacroHeadlines({ limit: 6 })
  const story = buildMarketNarrative(btc.data, eth.data, outlook)
  const nextEvent = outlook.key_events[0]
  const btcDay = horizon(btc.data, '1d')
  const lead = outlook.leads.find((item) => item.symbol === 'BTC-PERP')

  return <section className={`panel ${styles.brief}`} aria-labelledby="editorial-thesis-title">
    <header className={styles.head}>
      <div>
        <span className={styles.kicker}>Bitcoin weekly market outlook</span>
        <h3 id="editorial-thesis-title">{story.headline}</h3>
        <p>A plain-English edition for returning to the market after a day, a week or a month away.</p>
      </div>
      <span className={styles.asOf}>{new Date(edition.generated_at).toLocaleString()}<br />Levels refresh from live retained candles</span>
    </header>

    <div className={styles.storyGrid}>
      <article className={styles.prose}>
        <section><span>1 · The month and the week</span><p>{story.overview}</p><p>{story.week}</p></section>
        <section><span>2 · What matters in the next session</span><p>{story.session}</p><p>{story.ethereum}</p></section>
        <section><span>3 · The next known catalyst</span><p>{story.catalyst}</p>{nextEvent?.url && <a href={nextEvent.url} target="_blank" rel="noreferrer">Open the event source ↗</a>}</section>
      </article>
      <aside className={styles.chartCard}>
        <div className={styles.chartHead}><div><span>Picture</span><strong>Bitcoin · daily candles</strong></div><NavLink to="/canvas?symbol=BTC-PERP&interval=1d">Draw on full chart →</NavLink></div>
        {candles.isLoading && <p>Loading the retained Bitcoin chart…</p>}
        {candles.isError && <p>The chart is unavailable; no placeholder picture is substituted.</p>}
        {candles.data?.candles?.length ? <PriceChart candles={candles.data.candles} height={280} /> : null}
        <div className={styles.chartLevels}><span>Support <b>{price(btcDay?.levels?.recent_low ?? lead?.low_24h)}</b></span><span>Current <b>{price(btc.data?.outlook.last_close ?? lead?.last)}</b></span><span>Resistance <b>{price(btcDay?.levels?.recent_high ?? lead?.high_24h)}</b></span></div>
      </aside>
    </div>

    <div className={styles.scenarios}>
      <article><span>Strength is confirmed when</span><p>{story.bullCase}</p></article>
      <article><span>Wait when</span><p>{story.waitCase}</p></article>
      <article><span>The recovery is wrong when</span><p>{story.bearCase}</p></article>
    </div>

    <div className={styles.sources}>
      <strong>Sources and further context</strong>
      <NavLink to="/timeframes">Measured timeframes</NavLink>
      <NavLink to="/market">Hyperliquid market evidence</NavLink>
      <NavLink to="/canvas?symbol=BTC-PERP&interval=4h">Bitcoin Market Canvas</NavLink>
      {news.data?.headlines.slice(0, 3).map((item) => <a key={`${item.source}:${item.title}`} href={item.url} target="_blank" rel="noreferrer">{item.title} ↗</a>)}
    </div>

    <details className={styles.appendix}>
      <summary><span><strong>Evidence behind this thesis</strong><small>Open the measurements, coverage limits and unavailable feeds.</small></span><b>Show evidence ↓</b></summary>
      <div className={styles.evidenceGrid}>{compactEvidence('Bitcoin', btc.data)}{compactEvidence('Ethereum', eth.data)}</div>
      <div className={styles.coverage}>
        <p><strong>Available:</strong> retained Hyperliquid candles, volume, funding and open-interest context, measured chart levels, economic calendar, headlines and event reactions.</p>
        <p><strong>Not yet authoritative:</strong> total crypto market cap, BTC dominance, Fear &amp; Greed, ETF flows and true volume-at-price POC/VAH/VAL. TradeSync does not invent those values.</p>
        <p><strong>Context only:</strong> Hyperliquid TVL is {context.data?.providers.defillama.data.tvl_usd ? `$${(context.data.providers.defillama.data.tvl_usd / 1e9).toFixed(2)}B` : 'currently unavailable'} and is not a trade trigger.</p>
      </div>
    </details>
  </section>
}
