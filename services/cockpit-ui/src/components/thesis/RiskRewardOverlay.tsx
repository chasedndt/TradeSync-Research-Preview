import { useEffect, useRef } from 'react'
import type { ChartHandles } from '../canvas/chartTypes'
import styles from './InteractiveThesisPlayer.module.css'

interface Geometry { entry: number; stop: number; target: number; direction: 'LONG' | 'SHORT'; fromTime: number; toTime: number }

export function RiskRewardOverlay({ handles, geometry }: { handles: ChartHandles | null; geometry: Geometry | null }) {
  const root = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!handles || !geometry || !root.current) return
    let frame = 0
    const update = () => {
      const entry = handles.series.priceToCoordinate(geometry.entry)
      const stop = handles.series.priceToCoordinate(geometry.stop)
      const target = handles.series.priceToCoordinate(geometry.target)
      const left = handles.chart.timeScale().timeToCoordinate(geometry.fromTime as never)
      const right = handles.chart.timeScale().timeToCoordinate(geometry.toTime as never)
      const node = root.current
      if (node && entry != null && stop != null && target != null && left != null && right != null) {
        node.style.display = 'block'
        node.style.setProperty('--entry-y', `${entry}px`)
        node.style.setProperty('--target-y', `${target}px`)
        node.style.setProperty('--stop-y', `${stop}px`)
        node.style.setProperty('--plan-left', `${Math.min(left, right)}px`)
        node.style.setProperty('--plan-width', `${Math.max(80, Math.abs(right - left))}px`)
      } else if (node) node.style.display = 'none'
      // Lightweight Charts does not emit a public price-scale drag event in
      // v4. Sampling coordinates while this presentation layer is mounted
      // keeps it locked to both axes during drag, zoom and resize.
      frame = requestAnimationFrame(update)
    }
    update()
    return () => cancelAnimationFrame(frame)
  }, [geometry, handles])

  if (!geometry) return null
  return <div ref={root} className={styles.riskOverlay} aria-label={`Illustrative ${geometry.direction} geometry: entry ${geometry.entry}, target ${geometry.target}, stop ${geometry.stop}`}>
    <div className={styles.rewardZone}><span>target {geometry.target.toLocaleString()}</span></div>
    <div className={styles.riskZone}><span>stop {geometry.stop.toLocaleString()}</span></div>
    <div className={styles.entryLine}><span>entry {geometry.entry.toLocaleString()}</span></div>
  </div>
}
