/**
 * Colour by delivery stop, not by SKU.
 *
 * Operationally the stop is what a loader needs at a glance. Technically,
 * boxes in a load touch at arbitrary pairings, so every pair of fills has to be
 * separable -- and only three hues clear that bar on this surface (validated:
 * worst all-pairs CVD dE 9.2, normal vision 24.0). Past three stops the hues
 * repeat and the lightness shifts; identity is carried by the legend and the
 * detail panel, never by hue alone.
 */

export const STOP_COLOURS = ['#2a78d6', '#eb6834', '#1baf7a'] as const

export const SURFACE = '#fcfcfb'
export const SURFACE_DARK = '#1a1a19'
export const INK = '#0b0b0b'
export const INK_SECONDARY = '#52514e'
export const INK_MUTED = '#898781'
export const HAIRLINE = '#c3c2b7'
export const GOOD = '#0ca30c'
export const CRITICAL = '#d03b3b'
export const WARNING = '#fab219'

/** Distinct-enough shade for stop N, 1-based. */
export function stopColour(stop: number): string {
  const index = Math.max(stop - 1, 0)
  const base = STOP_COLOURS[index % STOP_COLOURS.length]
  const cycle = Math.floor(index / STOP_COLOURS.length)
  return cycle === 0 ? base : shade(base, cycle)
}

/** Darken by a fixed step per wrap of the hue list. */
function shade(hex: string, steps: number): string {
  const factor = Math.max(0.35, 1 - steps * 0.28)
  const value = parseInt(hex.slice(1), 16)
  const r = Math.round(((value >> 16) & 255) * factor)
  const g = Math.round(((value >> 8) & 255) * factor)
  const b = Math.round((value & 255) * factor)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}
