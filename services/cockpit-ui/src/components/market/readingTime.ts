/**
 * When a reading was taken, in words.
 *
 * Every market panel states the exact moment behind what it shows, so these
 * live in one place rather than being written again per panel.
 */

/** "2026-09-16 12:00:04 UTC" — the exact moment a reading was taken. */
export const exactUtc = (ms: number | null | undefined): string =>
  ms == null ? 'unknown' : `${new Date(ms).toISOString().replace('T', ' ').slice(0, 19)} UTC`

/** A duration in its two largest useful units: "4s", "3m 20s", "2h 5m". */
export function ageWords(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return 'unknown'
  const seconds = Math.max(0, Math.round(ms / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return seconds % 60 ? `${minutes}m ${seconds % 60}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return minutes % 60 ? `${hours}h ${minutes % 60}m` : `${hours}h`
}

/** The exact moment plus how long ago it was: "2026-09-16 12:00:04 UTC (4s ago)". */
export const readAt = (ms: number | null | undefined, now: number = Date.now()): string =>
  ms == null ? 'unknown' : `${exactUtc(ms)} (${ageWords(now - ms)} ago)`
