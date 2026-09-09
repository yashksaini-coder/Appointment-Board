const BASE = import.meta.env.VITE_API_URL ?? '/api'

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new Error('Cannot reach the server. Is the API running?')
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`)
  return body
}

const query = (filters) => {
  const params = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v),
  )
  return params.toString() ? `?${params}` : ''
}

export const api = {
  list: (filters = {}) => request(`/appointments${query(filters)}`),
  create: (data) => request('/appointments', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => request(`/appointments/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  complete: (id) => request(`/appointments/${id}/complete`, { method: 'POST' }),
  cancel: (id) => request(`/appointments/${id}/cancel`, { method: 'POST' }),
}
