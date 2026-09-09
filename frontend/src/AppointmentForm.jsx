import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { lane, toMinutes } from './lane'

const today = () => new Date().toLocaleDateString('en-CA')

const BLANK = {
  title: '',
  description: '',
  appointment_date: '',
  start_time: '09:00',
  end_time: '09:30',
}

// Mirrors the server rules so the common mistakes never cost a round trip.
// The server re-checks everything regardless; this is convenience, not trust.
function validate(values) {
  const errors = {}
  if (!values.title.trim()) errors.title = 'Enter a title'
  if (!values.appointment_date) errors.appointment_date = 'Pick a date'
  if (!values.start_time) errors.start_time = 'Pick a start time'
  if (!values.end_time) errors.end_time = 'Pick an end time'
  if (values.start_time && values.end_time && values.end_time <= values.start_time) {
    errors.end_time = 'End time must be after start time'
  }
  return errors
}

// Same half-open rule the database enforces: 10:00-11:00 and 11:00-12:00 are
// neighbours, not a clash.
const overlaps = (a, b) =>
  toMinutes(a.start_time) < toMinutes(b.end_time) &&
  toMinutes(a.end_time) > toMinutes(b.start_time)

export default function AppointmentForm({ appointment, onSave, onClose }) {
  const dialogRef = useRef(null)
  // Read today() lazily, at open time: a module-level default would offer
  // yesterday's date to a tab that has been open overnight.
  const [values, setValues] = useState(() =>
    appointment ? { ...BLANK, ...appointment } : { ...BLANK, appointment_date: today() },
  )
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [taken, setTaken] = useState(null)

  // <dialog>.showModal() gives focus trapping, Esc-to-close and the backdrop
  // for free — no modal library, no scroll-lock hack.
  useEffect(() => {
    dialogRef.current?.showModal()
  }, [])

  // Close the element rather than unmounting it: <dialog>.close() is what
  // returns focus to whatever opened the dialog. onClose then does the state
  // update, so Esc, Discard and a successful save all take one path.
  const dismiss = () => {
    if (dialogRef.current?.open) dialogRef.current.close()
    else onClose()
  }

  // Show what the chosen day already holds, so the slot clash is visible while
  // picking a time instead of arriving as an error after saving. Fetched here
  // rather than passed down, so the board's own filters cannot hide a blocker.
  useEffect(() => {
    if (!values.appointment_date) return setTaken([])
    let live = true
    setTaken(null) // unknown until this day's own answer arrives
    api
      .list({ date: values.appointment_date })
      .then((all) => {
        if (!live) return
        setTaken(all.filter((a) => a.status !== 'cancelled' && a.id !== appointment?.id))
      })
      .catch(() => live && setTaken(null))
    return () => { live = false }
  }, [values.appointment_date, appointment?.id])

  const set = (field) => (event) => {
    setValues((v) => ({ ...v, [field]: event.target.value }))
    setErrors((e) => ({ ...e, [field]: undefined }))
    setFormError('')
  }

  const timesUsable = values.start_time && values.end_time && values.end_time > values.start_time
  const clash = timesUsable && taken ? taken.find((a) => overlaps(a, values)) : null
  const unknown = taken === null

  async function handleSubmit(event) {
    event.preventDefault()
    const found = validate(values)
    setErrors(found)
    if (Object.keys(found).length) return

    setSaving(true)
    try {
      await onSave({
        title: values.title.trim(),
        description: values.description.trim(),
        appointment_date: values.appointment_date,
        start_time: values.start_time,
        end_time: values.end_time,
      })
      dismiss()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const attempt = timesUsable ? lane(values.start_time, values.end_time) : null

  return (
    <dialog ref={dialogRef} className="dialog" aria-labelledby="dialog-title" onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate>
        <h2 id="dialog-title">{appointment ? 'Edit appointment' : 'New appointment'}</h2>

        {formError && <p className="notice notice-error" role="alert">{formError}</p>}

        <label>
          <span>Title</span>
          <input
            value={values.title}
            onChange={set('title')}
            autoFocus
            maxLength={120}
            aria-invalid={!!errors.title}
            placeholder="Design review"
          />
          {errors.title && <em className="field-error">{errors.title}</em>}
        </label>

        <label>
          <span>Description <span className="optional">optional</span></span>
          <textarea
            value={values.description}
            onChange={set('description')}
            rows={2}
            maxLength={2000}
            placeholder="What is this appointment about?"
          />
        </label>

        <label>
          <span>Date</span>
          <input
            type="date"
            value={values.appointment_date}
            onChange={set('appointment_date')}
            aria-invalid={!!errors.appointment_date}
          />
          {errors.appointment_date && <em className="field-error">{errors.appointment_date}</em>}
        </label>

        <div className="row">
          <label>
            <span>Start time</span>
            <input
              type="time"
              value={values.start_time}
              onChange={set('start_time')}
              aria-invalid={!!errors.start_time}
              aria-describedby="availability-note"
            />
            {errors.start_time && <em className="field-error">{errors.start_time}</em>}
          </label>
          <label>
            <span>End time</span>
            <input
              type="time"
              value={values.end_time}
              onChange={set('end_time')}
              aria-invalid={!!errors.end_time}
              aria-describedby="availability-note"
            />
            {errors.end_time && <em className="field-error">{errors.end_time}</em>}
          </label>
        </div>

        <div className={`availability${clash || unknown ? ' availability-clash' : ''}`}>
          <div className="lane lane-wide" aria-hidden="true">
            {(taken || []).map((a) => {
              const geo = lane(a.start_time, a.end_time)
              if (geo.offScale) return null
              return (
                <span
                  key={a.id}
                  className={[
                    'lane-block', `lane-${a.status}`,
                    geo.clippedStart ? 'lane-clip-start' : '',
                    geo.clippedEnd ? 'lane-clip-end' : '',
                  ].join(' ')}
                  style={{ left: geo.left, width: geo.width }}
                />
              )
            })}
            {attempt && !attempt.offScale && (
              <span
                className={[
                  'lane-block lane-attempt', clash ? 'lane-clash' : '',
                  attempt.clippedStart ? 'lane-clip-start' : '',
                  attempt.clippedEnd ? 'lane-clip-end' : '',
                ].join(' ')}
                style={{ left: attempt.left, width: attempt.width }}
              />
            )}
          </div>
          <p className="availability-note" id="availability-note" role="status">
            {!timesUsable
              ? 'Pick a start and end time to check the day.'
              : unknown
                ? 'Could not check this day. The server will still refuse a clash.'
                : clash
                  ? `Taken: "${clash.title}" runs ${clash.start_time}–${clash.end_time}.`
                  : taken.length
                    ? 'This time is free.'
                    : 'Nothing else booked that day.'}
          </p>
        </div>

        <footer className="dialog-actions">
          <button type="button" className="btn" onClick={dismiss}>Discard</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving…' : appointment ? 'Save changes' : 'Add appointment'}
          </button>
        </footer>
      </form>
    </dialog>
  )
}
