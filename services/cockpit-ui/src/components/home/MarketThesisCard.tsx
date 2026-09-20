import { NavLink } from 'react-router-dom'
import { useEdition, useEditions } from '../../api/hooks/useEditions'
import { useHorizonPage } from '../../api/hooks/useHorizons'
import { hasOutlook } from '../thesis/guards'
import { buildMarketNarrative, horizon, price } from '../thesis/marketNarrative'
import { RegenerateControl } from '../thesis/RegenerateControl'
import styles from './Home.module.css'

/** A complete, deterministic home-page briefing for a trader returning after days or weeks away. */
export function MarketThesisCard() {
  const editions = useEditions(1)
  const listed = editions.data?.editions[0]
  const full = useEdition(listed?.id ?? null)
  const edition = full.data ?? listed
  const outlook = edition && hasOutlook(edition.outlook) ? edition.outlook : null
  const btc = useHorizonPage('BTC-PERP')
  const eth = useHorizonPage('ETH-PERP')
  const story = outlook ? buildMarketNarrative(btc.data, eth.data, outlook) : null
  const btcDay = horizon(btc.data, '1d')
  const lead = outlook?.leads.find((item) => item.symbol === 'BTC-PERP')

  return <section className={`panel ${styles.fullThesis}`} aria-labelledby="market-thesis-title">
    <div className="panel-heading">
      <div><h2 id="market-thesis-title">Bitcoin market thesis</h2><p>{edition ? `${edition.edition.replace('-', ' ')} edition · ${new Date(edition.generated_at).toUTCString().slice(5, 22)} UTC` : 'Loading the latest edition…'}</p></div>
      <div className={styles.thesisActions}><RegenerateControl withReason={false} /><NavLink to="/thesis" className="panel-action">Interactive thesis →</NavLink></div>
    </div>
    {(editions.isError || full.isError) && <p className="tone-bad" style={{ padding: '12px 17px' }}>The complete thesis record could not be loaded. No cached opinion is substituted.</p>}
    {edition && !outlook && <p className="tone-dim" style={{ padding: '12px 17px' }}>{edition.headline} · regenerate this legacy edition to add the complete outlook.</p>}
    {story && <>
      <article className={styles.editorialThesis}>
        <div className={styles.editorialCopy}>
          <span className={styles.editorialKicker}>The market in plain English</span>
          <h3>{story.headline}</h3>
          <p>{story.overview}</p>
          <p>{story.week}</p>
          <p>{story.session} {story.ethereum}</p>
        </div>
        <aside className={styles.levelPicture} aria-label="Bitcoin support and resistance picture">
          <span>Bitcoin decision map</span>
          <div className={styles.levelRail}><i /><b style={{ left: '18%' }}>Support<br />{price(btcDay?.levels?.recent_low ?? lead?.low_24h)}</b><b className={styles.currentLevel} style={{ left: '51%' }}>Now<br />{price(btc.data?.outlook.last_close ?? lead?.last)}</b><b style={{ left: '82%' }}>Resistance<br />{price(btcDay?.levels?.recent_high ?? lead?.high_24h)}</b></div>
          <NavLink to="/canvas?symbol=BTC-PERP&interval=4h">Open the live Bitcoin chart →</NavLink>
          <NavLink to="/thesis">Play the narrated chart thesis →</NavLink>
        </aside>
      </article>
      <div className={styles.plainScenarios}>
        <p><strong>What confirms strength:</strong> {story.bullCase}</p>
        <p><strong>What keeps us waiting:</strong> {story.waitCase}</p>
        <p><strong>What proves the recovery wrong:</strong> {story.bearCase}</p>
      </div>
    </>}
  </section>
}
