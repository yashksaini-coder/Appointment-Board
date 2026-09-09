import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import AppointmentForm from './AppointmentForm.jsx'
import { duration, lane } from './lane'

const COLUMNS = [
  { status: 'scheduled', name: 'Scheduled' },
  { status: 'completed', name: 'Completed' },
  { status: 'cancelled', name: 'Cancelled' },
]

// Statuses are terminal, so a card only ever travels left to right. Anything
// not listed here is not a drop target at all.
const DROPPABLE = { completed: 'complete', cancelled: 'cancel' }

const THEMES = [
  { value: 'light', label: 'Light' },
  { value: 'system', label: 'System' },
  { value: 'dark', label: 'Dark' },
]

const isoToday = () => new Date().toLocaleDateString('en-CA')

function dayLabel(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  const midnight = new Date()
  midnight.setHours(0, 0, 0, 0)
  const relative = { '-1': 'Yesterday', 0: 'Today', 1: 'Tomorrow' }[
    Math.round((date - midnight) / 86_400_000)
  ]
  const full = date.toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    // Only spell out the year when it is not the current one, so a date in
    // another year is never ambiguous.
    ...(y !== midnight.getFullYear() && { year: 'numeric' }),
  })
  return relative ? `${relative}, ${full}` : full
}

function groupByDate(appointments) {
  // The API sorts by date then start time, so insertion order is display order.
  const days = new Map()
  for (const a of appointments) {
    if (!days.has(a.appointment_date)) days.set(a.appointment_date, [])
    days.get(a.appointment_date).push(a)
  }
  return [...days.entries()]
}

// "system" means no attribute at all, which leaves the prefers-color-scheme
// media query in charge -- so the board follows the OS live, with no listener.
function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem('theme')
      return THEMES.some((t) => t.value === saved) ? saved : 'system'
    } catch {
      return 'system'
    }
  })

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('theme', theme)
    } catch {
      // Private browsing or blocked storage: the choice just will not persist.
    }
  }, [theme])

  return [theme, setTheme]
}

function ThemeChoice({ theme, onChange }) {
  return (
    <div className="themes" role="group" aria-label="Colour theme">
      {THEMES.map((t) => (
        <button
          key={t.value}
          type="button"
          aria-pressed={theme === t.value}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function Bar({ appointment }) {
  const geo = lane(appointment.start_time, appointment.end_time)
  if (geo.offScale) {
    return <p className="lane-offscale">Outside the 06:00–22:00 scale</p>
  }
  return (
    <div className="lane" aria-hidden="true">
      <span
        className={[
          'lane-block',
          `lane-${appointment.status}`,
          geo.clippedStart ? 'lane-clip-start' : '',
          geo.clippedEnd ? 'lane-clip-end' : '',
        ].join(' ')}
        style={{ left: geo.left, width: geo.width }}
      />
    </div>
  )
}

function Card({
  appointment, busy, confirming, canDrag,
  onEdit, onComplete, onCancel, onArm, onDisarm, onDragStart, onDragEnd,
}) {
  const live = appointment.status === 'scheduled'
  const titleId = `appt-${appointment.id}-title`
  const promptId = `appt-${appointment.id}-prompt`

  const cancelRef = useRef(null)
  const confirmRef = useRef(null)
  const wasConfirming = useRef(false)

  // Swapping the action row for the confirmation destroys the focused button.
  // Move focus onto whichever block just mounted, and hand it back on disarm,
  // or a keyboard user is dropped to the top of the document mid-task.
  useEffect(() => {
    if (confirming && !wasConfirming.current) confirmRef.current?.focus()
    else if (!confirming && wasConfirming.current) cancelRef.current?.focus()
    wasConfirming.current = confirming
  }, [confirming])

  return (
    <article
      className={`card card-${appointment.status}${busy ? ' is-busy' : ''}`}
      aria-labelledby={titleId}
      draggable={live && canDrag && !busy}
      onDragStart={live && canDrag ? (e) => onDragStart(e, appointment) : undefined}
      onDragEnd={live && canDrag ? onDragEnd : undefined}
    >
      <div className="card-top">
        {live && canDrag && <span className="grip" aria-hidden="true" />}
        <span className="card-time">
          {appointment.start_time}–{appointment.end_time}
        </span>
        <span className="card-duration">
          {duration(appointment.start_time, appointment.end_time)}
        </span>
      </div>

      <h3 className="card-title" id={titleId}>{appointment.title}</h3>
      {appointment.description && <p className="card-note">{appointment.description}</p>}

      <Bar appointment={appointment} />

      {!live && (
        <p className="card-state">
          {appointment.status === 'completed' ? 'Completed' : 'Cancelled, time slot released'}
        </p>
      )}

      {live && !confirming && (
        <div className="card-actions">
          <button className="btn btn-sm" onClick={onEdit} disabled={busy}
                  aria-label={`Edit "${appointment.title}"`}>
            Edit
          </button>
          <button className="btn btn-sm" onClick={onComplete} disabled={busy}
                  aria-label={`Mark complete: "${appointment.title}"`}>
            Mark complete
          </button>
          <button className="btn btn-sm" onClick={onArm} disabled={busy} ref={cancelRef}
                  aria-label={`Cancel "${appointment.title}"`}>
            Cancel
          </button>
        </div>
      )}

      {live && confirming && (
        <div className="card-confirm">
          <p id={promptId}>
            Cancel this appointment? It stays on the board and the time slot opens up.
          </p>
          <div className="card-actions">
            <button className="btn btn-sm" onClick={onCancel} disabled={busy}
                    ref={confirmRef} aria-describedby={promptId}
                    aria-label={`Cancel appointment: "${appointment.title}"`}>
              Cancel appointment
            </button>
            <button className="btn btn-sm" onClick={onDisarm} disabled={busy}
                    aria-label={`Keep it: "${appointment.title}"`}>
              Keep it
            </button>
          </div>
        </div>
      )}
    </article>
  )
}

export default function App() {
  const [appointments, setAppointments] = useState([])
  const [filters, setFilters] = useState({ date: '', status: '' })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [editing, setEditing] = useState(null)
  const [busyIds, setBusyIds] = useState(() => new Set())
  const [confirmingId, setConfirmingId] = useState(null)
  const [dragging, setDragging] = useState(null)
  const [dropTarget, setDropTarget] = useState(null)
  const [toast, setToast] = useState(null)
  const [theme, setTheme] = useTheme()

  const requestSeq = useRef(0)
  const bandRefs = useRef({})

  const notify = useCallback((kind, text) => {
    // The counter makes a repeated identical message still mutate the live
    // region's text node, so screen readers announce it again.
    setToast((t) => ({ kind, text, n: (t?.n ?? 0) + 1 }))
  }, [])

  useEffect(() => {
    // Errors stay until dismissed; only good news disappears on its own.
    if (!toast || toast.kind === 'error') return
    const timer = setTimeout(() => setToast(null), 6000)
    return () => clearTimeout(timer)
  }, [toast])

  const load = useCallback(async () => {
    // Every filter keystroke starts a request. Without a sequence guard a slow
    // earlier response can land last and leave the board showing stale rows.
    const seq = ++requestSeq.current
    setLoading(true)
    try {
      const rows = await api.list(filters)
      if (seq !== requestSeq.current) return
      setAppointments(rows)
      setLoadError('')
    } catch (err) {
      if (seq !== requestSeq.current) return
      setLoadError(err.message)
    } finally {
      if (seq === requestSeq.current) setLoading(false)
    }
  }, [filters])

  useEffect(() => { load() }, [load])

  const columns = filters.status
    ? COLUMNS.filter((c) => c.status === filters.status)
    : COLUMNS

  const counts = useMemo(() => {
    const tally = { scheduled: 0, completed: 0, cancelled: 0 }
    for (const a of appointments) tally[a.status] += 1
    return tally
  }, [appointments])

  const days = useMemo(() => groupByDate(appointments), [appointments])

  async function act(appointment, action, successText) {
    const { id } = appointment
    setBusyIds((s) => new Set(s).add(id))
    try {
      await action()
      notify('success', successText)
      setConfirmingId((c) => (c === id ? null : c))
      await load()
      // The card just unmounted from under the keyboard. Park focus on the day
      // it belonged to rather than losing it to the top of the document.
      bandRefs.current[appointment.appointment_date]?.focus()
    } catch (err) {
      notify('error', err.message)
    } finally {
      setBusyIds((s) => {
        const next = new Set(s)
        next.delete(id)
        return next
      })
    }
  }

  const complete = (a) =>
    act(a, () => api.complete(a.id), `"${a.title}" marked complete.`)
  const cancel = (a) =>
    act(a, () => api.cancel(a.id), `"${a.title}" cancelled. The time slot is free again.`)

  async function save(data) {
    const isEdit = editing !== 'new'
    await (isEdit ? api.update(editing.id, data) : api.create(data))
    // The form closes the <dialog> itself on success, which returns focus to
    // the opener; onClose then clears `editing` here.
    notify('success', isEdit ? `"${data.title}" updated.` : `"${data.title}" added to the board.`)
    await load()
  }

  function handleDrop(status) {
    const moving = dragging
    setDropTarget(null)
    setDragging(null)
    if (!moving || !DROPPABLE[status]) return
    if (status === 'completed') complete(moving)
    else {
      // Cancelling is not undoable, so a drop arms the card's own confirmation
      // rather than acting on it. Say so, or the drop looks like it did nothing.
      setConfirmingId(moving.id)
      notify('success', `Confirm on the card to cancel "${moving.title}".`)
    }
  }

  const filtered = filters.date || filters.status
  // Dragging needs somewhere to drop. With a status filter on, the other
  // columns are not rendered, so the affordance would be a dead end.
  const canDrag = columns.length === COLUMNS.length

  const tally = loading
    ? 'Loading…'
    : filters.status
      ? `${counts[filters.status]} ${filters.status}`
      : `${counts.scheduled} scheduled, ${counts.completed} completed, ${counts.cancelled} cancelled`

  return (
    <div className="page">
      {/* Both regions are always mounted and start empty: a live region that
          appears at the same moment as its text is often missed entirely. */}
      <div className="sr-only" role="status" aria-live="polite">
        {toast?.kind === 'success' ? toast.text : ''}
      </div>
      <div className="sr-only" role="alert">
        {toast?.kind === 'error' ? toast.text : ''}
      </div>

      {toast && (
        <div className={`toast toast-${toast.kind}`} aria-hidden="true">
          <span>{toast.text}</span>
          <button className="toast-close" onClick={() => setToast(null)} aria-label="Dismiss message">
            ×
          </button>
        </div>
      )}

      <header className="masthead">
        <div>
          <h1>Appointment board</h1>
          <p className="standfirst">
            Every bar shows where the appointment sits in the day, on the same 06:00 to 22:00
            scale. Appointments move one way: scheduled, then completed or cancelled.
          </p>
        </div>
        <div className="masthead-tools">
          <ThemeChoice theme={theme} onChange={setTheme} />
          <button className="btn btn-primary" onClick={() => setEditing('new')}>
            Add appointment
          </button>
        </div>
      </header>

      <div className="controls">
        <label>
          <span>Date</span>
          <input
            type="date"
            value={filters.date}
            onChange={(e) => setFilters((f) => ({ ...f, date: e.target.value }))}
          />
        </label>
        <label>
          <span>Status</span>
          <select
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          >
            <option value="">All three columns</option>
            {COLUMNS.map((c) => (
              <option key={c.status} value={c.status}>{c.name} only</option>
            ))}
          </select>
        </label>
        <button className="btn" onClick={() => setFilters({ date: '', status: '' })} disabled={!filtered}>
          Clear filters
        </button>
        <p className="tally">{tally}</p>
      </div>

      {loadError && (
        <p className="notice notice-error" role="alert">
          {loadError} <button className="btn btn-sm" onClick={load}>Try again</button>
        </p>
      )}

      <section
        className="board"
        style={{ '--columns': columns.length }}
        aria-label="Appointments by status"
      >
        <div className="board-head" aria-hidden="true">
          {columns.map((c) => (
            <div key={c.status} className={`head head-${c.status}`}>
              <span className="head-name">{c.name}</span>
              <span className="head-count">{counts[c.status]}</span>
            </div>
          ))}
        </div>

        {!loading && !loadError && appointments.length === 0 && (
          <p className="notice">
            {filtered
              ? 'No appointments match these filters.'
              : 'The board is empty. Add the first appointment.'}
          </p>
        )}

        {days.map(([date, forDay]) => (
          <div className="day" key={date}>
            <h2
              className={`day-band${date === isoToday() ? ' day-band-today' : ''}`}
              tabIndex={-1}
              ref={(el) => { bandRefs.current[date] = el }}
            >
              {dayLabel(date)}
            </h2>
            <div className="day-row">
              {columns.map((c) => {
                const cards = forDay.filter((a) => a.status === c.status)
                // Only this card's own day accepts it: a drop never changes a
                // date, so lighting up another band would promise a move the
                // board cannot make.
                const droppable =
                  dragging && DROPPABLE[c.status] && dragging.appointment_date === date
                return (
                  <div
                    key={c.status}
                    role="group"
                    aria-label={`${dayLabel(date)}, ${c.name}`}
                    data-column={c.name}
                    className={[
                      'cell',
                      droppable ? 'cell-droppable' : '',
                      dropTarget === `${date}:${c.status}` ? `cell-over cell-over-${c.status}` : '',
                    ].join(' ')}
                    onDragOver={droppable ? (e) => {
                      e.preventDefault()
                      setDropTarget(`${date}:${c.status}`)
                    } : undefined}
                    onDragLeave={droppable ? () => setDropTarget(null) : undefined}
                    onDrop={droppable ? (e) => { e.preventDefault(); handleDrop(c.status) } : undefined}
                  >
                    {cards.map((a) => (
                      <Card
                        key={a.id}
                        appointment={a}
                        busy={busyIds.has(a.id)}
                        confirming={confirmingId === a.id}
                        canDrag={canDrag}
                        onEdit={() => setEditing(a)}
                        onComplete={() => complete(a)}
                        onCancel={() => cancel(a)}
                        onArm={() => setConfirmingId(a.id)}
                        onDisarm={() => setConfirmingId(null)}
                        onDragStart={(e, appt) => {
                          e.dataTransfer.effectAllowed = 'move'
                          e.dataTransfer.setData('text/plain', String(appt.id))
                          setDragging(appt)
                        }}
                        onDragEnd={() => { setDragging(null); setDropTarget(null) }}
                      />
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </section>

      {editing && (
        <AppointmentForm
          key={editing === 'new' ? 'new' : editing.id}
          appointment={editing === 'new' ? null : editing}
          onSave={save}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}
