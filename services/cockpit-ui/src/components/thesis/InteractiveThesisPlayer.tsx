import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Maximize2, Minimize2 } from 'lucide-react'
import type { Candle, ThesisEdition } from '../../api/types'
import { useCandles } from '../../api/hooks/useCandles'
import { PriceChart } from '../canvas/PriceChart'
import type { ChartHandles, EvidenceMarker } from '../canvas/chartTypes'
import { formatPrice } from '../canvas/format'
import { HorizonLens } from './HorizonLens'
import { detectStructure } from './marketStructure'
import { buildPlaybackScenes, parseSrt, PLAYBACK_INTERVALS, sceneIndexAtTime, sceneLevels, type PlaybackInterval } from './playback'
import { RiskRewardOverlay } from './RiskRewardOverlay'
import styles from './InteractiveThesisPlayer.module.css'

const MEDIA_BASE = '/api/state/thesis/editions'

function clock(seconds: number) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0
  return `${Math.floor(safe / 60)}:${Math.floor(safe % 60).toString().padStart(2, '0')}`
}

function currentMarker(candles: Candle[], direction: 'LONG' | 'SHORT' | 'NONE'): EvidenceMarker[] {
  // Leave enough bars to the marker's right for its explanatory label. This is
  // a playback illustration, not a claim that an entry occurred on the newest bar.
  const anchor = candles[Math.max(0, candles.length - 12)]
  if (!anchor || direction === 'NONE') return []
  return [{ time: anchor.time, direction, label: `EXAMPLE ${direction}`, kind: 'change' }]
}

export function InteractiveThesisPlayer({ edition }: { edition: ThesisEdition }) {
  const playerRef = useRef<HTMLElement | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [cues, setCues] = useState<ReturnType<typeof parseSrt>>([])
  const [sceneIndex, setSceneIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [audioError, setAudioError] = useState('')
  const [showPlan, setShowPlan] = useState(true)
  const [showCaptions, setShowCaptions] = useState(true)
  const [chartHandles, setChartHandles] = useState<ChartHandles | null>(null)
  const [manualInterval, setManualInterval] = useState<PlaybackInterval | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const scenes = useMemo(() => buildPlaybackScenes(edition, cues), [edition, cues])
  const scene = scenes[Math.min(sceneIndex, Math.max(0, scenes.length - 1))]
  const displayInterval = manualInterval ?? scene?.interval ?? '1d'
  const displayScene = scene ? { ...scene, interval: displayInterval } : undefined
  const thesis = scene ? edition.theses?.[scene.symbol] : undefined
  const candleQuery = useCandles(scene?.symbol ?? '', displayInterval, 260)
  const candles = candleQuery.data?.candles ?? []
  const levels = useMemo(() => displayScene ? sceneLevels(edition, displayScene) : [], [edition, displayScene])
  const markers = useMemo(() => scene?.phase === 'scenario' ? currentMarker(candles, thesis?.structure.direction ?? 'NONE') : [], [candles, scene?.phase, thesis?.structure.direction])
  const sceneProgress = scene
    ? Math.max(0, Math.min(1, (currentTime - scene.start) / Math.max(0.1, scene.end - scene.start)))
    : 0
  const revealedCount = playing ? Math.max(1, Math.ceil(levels.length * sceneProgress)) : levels.length
  const visibleLevels = levels.slice(0, revealedCount)
  const visibleMarkers = scene?.phase === 'scenario' && (!playing || sceneProgress >= 0.55) ? markers : []
  const audioUrl = edition.media.audio ? `${MEDIA_BASE}/${edition.id}/media/${edition.media.audio}` : ''
  const activeCue = cues.findIndex((cue) => currentTime >= cue.start && currentTime < cue.end)
  const structure = useMemo(() => detectStructure(candles), [candles])
  const geometry = useMemo(() => {
    if (!thesis || thesis.structure.direction === 'NONE') return null
    const entry = thesis.anchors.last_close
    const stop = thesis.invalidation.level
    const target = thesis.structure.direction === 'LONG' ? thesis.anchors.high_24h : thesis.anchors.low_24h
    if (!entry || !stop || !target) return null
    if (thesis.structure.direction === 'LONG' && !(stop < entry && target > entry)) return null
    if (thesis.structure.direction === 'SHORT' && !(target < entry && stop > entry)) return null
    const fromTime = candles[Math.max(0, candles.length - 50)]?.time
    const toTime = candles[Math.max(0, candles.length - 8)]?.time
    if (!fromTime || !toTime) return null
    return { entry, stop, target, direction: thesis.structure.direction, fromTime, toTime }
  }, [candles, thesis])
  const keywords = useMemo(() => {
    const candidates = [scene?.symbol.replace('-PERP', ''), 'trend', 'range', 'momentum', 'invalidation', 'funding', 'liquidity', 'risk']
    return candidates.filter((word): word is string => Boolean(word && cues.some((cue) => cue.text.toLowerCase().includes(word.toLowerCase()))))
      .map((word) => ({ word, cue: cues.findIndex((cue) => cue.text.toLowerCase().includes(word.toLowerCase())) }))
  }, [cues, scene?.symbol])

  useEffect(() => {
    setCues([])
    setSceneIndex(0)
    setCurrentTime(0)
    setPlaying(false)
    const subtitle = edition.media.subtitles
    if (!subtitle) return
    const controller = new AbortController()
    void fetch(`${MEDIA_BASE}/${edition.id}/media/${subtitle}`, { signal: controller.signal })
      .then((response) => response.ok ? response.text() : Promise.reject(new Error('Subtitle timing unavailable')))
      .then((text) => setCues(parseSrt(text)))
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== 'AbortError') setAudioError('Subtitle timing unavailable; using the deterministic chapter clock.')
      })
    return () => controller.abort()
  }, [edition.id, edition.media.subtitles])

  useEffect(() => {
    setSceneIndex((current) => Math.min(current, Math.max(0, scenes.length - 1)))
  }, [scenes.length])

  useEffect(() => {
    setManualInterval(null)
  }, [scene?.id])

  useEffect(() => {
    const onFullscreen = () => setFullscreen(document.fullscreenElement === playerRef.current)
    document.addEventListener('fullscreenchange', onFullscreen)
    return () => document.removeEventListener('fullscreenchange', onFullscreen)
  }, [])

  const goToScene = (index: number, resume = false) => {
    const next = scenes[index]
    if (!next) return
    setSceneIndex(index)
    setCurrentTime(next.start)
    if (audioRef.current) audioRef.current.currentTime = next.start
    if (resume && audioRef.current) void audioRef.current.play()
  }

  const seek = (time: number) => {
    if (audioRef.current) audioRef.current.currentTime = time
    setCurrentTime(time)
    setSceneIndex(sceneIndexAtTime(scenes, time))
  }

  const toggle = async () => {
    const audio = audioRef.current
    if (!audio) return
    setAudioError('')
    try {
      if (audio.paused) await audio.play()
      else audio.pause()
    } catch {
      setAudioError('The browser refused audio playback. Press Play again after interacting with the page.')
    }
  }

  const chooseInterval = (interval: PlaybackInterval) => {
    audioRef.current?.pause()
    setManualInterval(interval)
  }

  const chooseSymbol = (symbol: string) => {
    const index = scenes.findIndex((candidate) => candidate.symbol === symbol)
    const fallback = scenes.findIndex((candidate) => candidate.symbol === symbol)
    audioRef.current?.pause()
    goToScene(index >= 0 ? index : fallback)
  }

  if (!scene) return null
  const last = candles[candles.length - 1]
  const verdict = thesis?.verdict ?? 'NO STORED THESIS'
  const direction = thesis?.structure.direction ?? 'NONE'
  const activeCaption = activeCue >= 0 ? cues[activeCue]?.text : scene.narration

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await playerRef.current?.requestFullscreen()
    } catch {
      setAudioError('Fullscreen is unavailable in this browser window.')
    }
  }

  return (
    <section ref={playerRef} className={`panel ${styles.player} ${fullscreen ? styles.fullscreen : ''}`} aria-labelledby="interactive-thesis-title">
      <header className={styles.head}>
        <div>
          <h3 id="interactive-thesis-title">Interactive thesis playback</h3>
          <p>ChaseOS narration drives real Hyperliquid candles, timeframe changes and temporary presentation annotations.</p>
        </div>
        <div className={styles.headActions}><div className={styles.mode}><span>LIVE CHART STORY</span><span>display only · no orders</span></div><button type="button" className={styles.fullscreenButton} onClick={() => void toggleFullscreen()}>{fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />} {fullscreen ? 'Exit' : 'Theater'}</button></div>
      </header>

      <div className={styles.body}>
        <div className={styles.stage}>
          <div className={styles.chartHead}>
            <strong>{scene.symbol.replace('-PERP', '')} / USD</strong>
            <span>{displayInterval} · HYPERLIQUID · {candleQuery.isFetching ? 'updating' : 'measured'}</span>
            <label className={styles.overlayToggle}><input type="checkbox" checked={showPlan} onChange={(event) => setShowPlan(event.target.checked)} /> scenario overlay</label>
          </div>
          <div className={styles.chart}>
            <div className={styles.chartBadge} key={scene.id}>
              <strong>{scene.title}</strong>
              <span>{levels.length ? `${visibleLevels.length} of ${levels.length} stored thesis levels drawn` : 'No stored price levels for this chapter'}</span>
              <span>{sceneIndex + 1} / {scenes.length} · {scene.phase === 'scenario' ? 'trade geometry follows the completed briefing' : 'context first · no position drawing yet'}</span>
              {scene.phase === 'scenario' && direction !== 'NONE' && <span className={styles.paperMarker}>Temporary paper illustration: {visibleMarkers.length ? direction : 'waiting for this chapter'} · removed at the next chapter</span>}
            </div>
            {candleQuery.isError ? <div className={styles.empty}>Candles unavailable; no substitute chart is drawn.</div>
              : candleQuery.isLoading ? <div className={styles.empty}>Loading measured candles…</div>
                : candles.length === 0 ? <div className={styles.empty}>No venue candles returned for this chapter.</div>
                  : <><PriceChart key={`${scene.symbol}:${displayInterval}`} candles={candles} markers={visibleMarkers} levels={visibleLevels} height={fullscreen ? 620 : 500} onReady={setChartHandles} />
                    {showPlan && scene.phase === 'scenario' && <RiskRewardOverlay handles={chartHandles} geometry={geometry} />}
                    {showCaptions && activeCaption && <div className={`${styles.liveCaption} ${scene.phase === 'scenario' ? styles.liveCaptionScenario : ''}`}><span>{clock(currentTime)}</span><p>{activeCaption}</p></div>}</>}
          </div>
        </div>

        <aside className={styles.side}>
          <audio
            ref={audioRef}
            src={audioUrl}
            preload="metadata"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
            onTimeUpdate={(event) => {
              const time = event.currentTarget.currentTime
              setCurrentTime(time)
              setSceneIndex(sceneIndexAtTime(scenes, time))
            }}
            onEnded={() => setPlaying(false)}
          />
          <div className={styles.controls}>
            <button type="button" className={`${styles.control} ${styles.play}`} onClick={() => void toggle()} disabled={!audioUrl}>{playing ? 'Pause' : 'Play'}</button>
            <button type="button" className={styles.control} onClick={() => goToScene(Math.max(0, sceneIndex - 1))} aria-label="Previous chapter">←</button>
            <input className={styles.progress} type="range" min={0} max={duration || scenes[scenes.length - 1]?.end || 1} step={0.1} value={currentTime} aria-label="Thesis playback position" onChange={(event) => {
              const next = Number(event.target.value)
              seek(next)
            }} />
            <span className={styles.time}>{clock(currentTime)} / {clock(duration || scenes[scenes.length - 1]?.end || 0)}</span>
          </div>

          <div><p className={styles.label}>Inspect this chapter at</p><div className={styles.chips}>{PLAYBACK_INTERVALS.map((interval) => <button key={interval} type="button" className={`${styles.chip} ${displayInterval === interval ? styles.chipActive : ''}`} onClick={() => chooseInterval(interval)}>{interval}</button>)}</div></div>
          <div><p className={styles.label}>Market chapter</p><div className={styles.chips}>{edition.symbols.map((symbol) => <button key={symbol} type="button" className={`${styles.chip} ${scene.symbol === symbol ? styles.chipActive : ''}`} onClick={() => chooseSymbol(symbol)}>{symbol.replace('-PERP', '')}</button>)}</div></div>

          <div className={styles.chapter} key={`${scene.id}:text`}>
            <strong>{scene.title}</strong>
            <p>{scene.narration}</p>
          </div>
          <HorizonLens symbol={scene.symbol} interval={displayInterval} />
          {structure && <div className={styles.structure}><span>{structure.authority}</span><strong>{structure.label}</strong><p>{structure.detail}</p></div>}
          <div className={styles.facts}>
            <span>Stored verdict</span><b>{verdict}</b>
            <span>Paper direction</span><b className={direction === 'LONG' ? 'tone-good' : direction === 'SHORT' ? 'tone-bad' : 'tone-dim'}>{direction}</b>
            <span>Last candle</span><b>{last ? formatPrice(last.close) : '—'}</b>
            <span>Market state</span><b>{thesis?.structure.entry_regime?.replace(/_/g, ' ') || '—'}</b>
          </div>
          <div className={styles.captionControls}>
            <button type="button" onClick={() => setShowCaptions((value) => !value)}>{showCaptions ? 'Hide' : 'Show'} captions</button>
            <div>{keywords.map(({ word, cue }) => <button key={word} type="button" onClick={() => seek(cues[cue].start)}>{word}</button>)}</div>
          </div>
          {showCaptions && <div className={styles.captions} aria-label="Clickable thesis transcript">{cues.map((cue, index) => <button key={`${cue.start}:${index}`} type="button" className={index === activeCue ? styles.captionActive : ''} onClick={() => seek(cue.start)}><time>{clock(cue.start)}</time><span>{cue.text}</span></button>)}</div>}
          {audioError && <p className="tone-bad" role="status">{audioError}</p>}
          <NavLink className={styles.canvasLink} to={`/canvas?symbol=${encodeURIComponent(scene.symbol)}&interval=${displayInterval}&view=chart`}>Open this chapter in Market Canvas →</NavLink>
          <NavLink className={styles.opportunityLink} to="/opportunities">Inspect measured opportunities and paper-entry gates →</NavLink>
          <p className={styles.foot}>Lines, structure labels and risk/reward geometry are explanatory overlays. They disappear as chapters change and are never saved as drawings, signals or orders. A plan appears only when the edition contains valid entry, invalidation and target-side anchors.</p>
        </aside>
      </div>

      {edition.media.video && <details className={styles.fallback}><summary>Rendered MP4 fallback</summary><video controls preload="metadata" src={`${MEDIA_BASE}/${edition.id}/media/${edition.media.video}`} /></details>}
    </section>
  )
}
