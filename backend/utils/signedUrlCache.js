// Tiny in-memory cache for signed URLs to avoid re-signing on every list call.
// App Runner instances are ephemeral; this is best-effort only.

const CACHE = new Map()

function nowMs() {
  return Date.now()
}

function get(key) {
  const k = String(key || '')
  if (!k) return null
  const v = CACHE.get(k)
  if (!v) return null
  if (v.expiresAtMs && nowMs() >= v.expiresAtMs) {
    CACHE.delete(k)
    return null
  }
  return v
}

function set(key, value) {
  const k = String(key || '')
  if (!k) return
  if (!value || typeof value !== 'object') return
  CACHE.set(k, value)
}

function clearExpired() {
  const t = nowMs()
  for (const [k, v] of CACHE.entries()) {
    if (v?.expiresAtMs && t >= v.expiresAtMs) CACHE.delete(k)
  }
}

module.exports = { get, set, clearExpired }
