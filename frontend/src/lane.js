// The board draws every appointment against one fixed day scale, so two bars
// anywhere on screen are directly comparable. 06:00-22:00 covers a working day
// with room either side; anything outside is clamped and flagged so the bar
// never lies about where it sits.
export const DAY_START = 6 * 60
export const DAY_END = 22 * 60
const SPAN = DAY_END - DAY_START

export const toMinutes = (hhmm) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

export function lane(start, end) {
  const rawStart = toMinutes(start)
  const rawEnd = toMinutes(end)
  const s = Math.min(Math.max(rawStart, DAY_START), DAY_END)
  const e = Math.min(Math.max(rawEnd, DAY_START), DAY_END)
  const left = ((s - DAY_START) / SPAN) * 100
  // A 15-minute appointment is 1.6% of the scale, which disappears. Floor it.
  const width = Math.max(1.6, ((e - s) / SPAN) * 100)
  return {
    left: `${left}%`,
    width: `${Math.min(width, 100 - left)}%`,
    clippedStart: rawStart < DAY_START,
    clippedEnd: rawEnd > DAY_END,
    // Wholly outside the window. Clamping would paint a bar at 06:00 or 22:00
    // that asserts a time the appointment does not occupy, so callers show a
    // note instead of a block.
    offScale: rawEnd <= DAY_START || rawStart >= DAY_END,
  }
}

export function duration(start, end) {
  const mins = toMinutes(end) - toMinutes(start)
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (h && m) return `${h} hr ${m} min`
  return h ? `${h} hr` : `${m} min`
}
