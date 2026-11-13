// Client gọi API Python. Không cache: dữ liệu luôn là trạng thái mới nhất.
export const API_BASE = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8787'

export async function api(path, { method = 'GET', body, asText = false } = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: 'no-store',
  })
  const raw = await response.text()
  let data = raw
  try {
    data = raw ? JSON.parse(raw) : null
  } catch {
    data = raw
  }
  if (!response.ok) {
    const detail = data && typeof data === 'object' ? data.detail : data
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${response.status}`)
  }
  return asText ? raw : data
}

export const get = (path) => api(path)
export const post = (path, body) => api(path, { method: 'POST', body })
export const put = (path, body) => api(path, { method: 'PUT', body })
export const del = (path, body) => api(path, { method: 'DELETE', body })

// ---------------- định dạng hiển thị ----------------
export const STATUS_TONE = {
  'Hoạt động': 'ok',
  'Không hoạt động': 'error',
  'Chưa kiểm tra': 'muted',
  'Đang mở': 'ok',
  'Chưa mở': 'warn',
  'Đã đóng': 'muted',
  'Chưa rõ': 'info',
  paused: 'info',
  registered: 'ok',
  already: 'ok',
  closed: 'muted',
  error: 'error',
  login_failed: 'error',
  ip_blocked: 'warn',
  dry_run: 'info',
  unverified: 'warn',
}

export function tone(status) {
  return STATUS_TONE[status] || 'muted'
}

export function shortTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 19)
}

export function pct(done, total) {
  if (!total) return 0
  return Math.min(100, Math.round((done / total) * 100))
}
