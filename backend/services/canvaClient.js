const axios = require('axios')
const crypto = require('crypto')
const { encryptString, decryptString } = require('../utils/tokenCrypto')
const canvaDb = require('../db/canva')

const CANVA_API_BASE = 'https://api.canva.com/rest'
const CANVA_AUTH_URL = 'https://www.canva.com/api/oauth/authorize'
const CANVA_TOKEN_URL = 'https://api.canva.com/rest/v1/oauth/token'

function requiredEnv(name) {
  const v = process.env[name]
  if (!v) {
    const err = new Error(`${name} is not configured`)
    err.code = 'missing_config'
    throw err
  }
  return v
}

function generatePkcePair() {
  // Canva requires PKCE (S256). Use a high-entropy verifier per request.
  const codeVerifier = crypto.randomBytes(96).toString('base64url')
  const codeChallenge = crypto
    .createHash('sha256')
    .update(codeVerifier)
    .digest('base64url')
  return { codeVerifier, codeChallenge }
}

function buildAuthorizeUrl({ state, scopes, codeChallenge }) {
  const clientId = requiredEnv('CANVA_CLIENT_ID')
  const redirectUri = requiredEnv('CANVA_REDIRECT_URI')
  const url = new URL(CANVA_AUTH_URL)
  url.searchParams.set('client_id', clientId)
  url.searchParams.set('redirect_uri', redirectUri)
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('state', state)
  if (codeChallenge) {
    url.searchParams.set('code_challenge_method', 's256')
    url.searchParams.set('code_challenge', String(codeChallenge))
  }
  if (Array.isArray(scopes) && scopes.length > 0) {
    url.searchParams.set('scope', scopes.join(' '))
  }
  return url.toString()
}

function basicAuthHeaderValue() {
  const clientId = requiredEnv('CANVA_CLIENT_ID')
  const clientSecret = requiredEnv('CANVA_CLIENT_SECRET')
  const credentials = Buffer.from(
    `${clientId}:${clientSecret}`,
    'utf8',
  ).toString('base64')
  return `Basic ${credentials}`
}

async function exchangeCodeForToken(code, codeVerifier) {
  const redirectUri = requiredEnv('CANVA_REDIRECT_URI')
  if (!codeVerifier) {
    const err = new Error('Missing PKCE code_verifier')
    err.code = 'missing_pkce'
    throw err
  }

  const body = new URLSearchParams()
  body.set('grant_type', 'authorization_code')
  // Canva requires PKCE for auth code exchange.
  body.set('code_verifier', String(codeVerifier || ''))
  body.set('redirect_uri', redirectUri)
  body.set('code', code)

  const resp = await axios.post(CANVA_TOKEN_URL, body.toString(), {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: basicAuthHeaderValue(),
      // Some OAuth providers require client_id even with Basic auth; harmless to include.
    },
    timeout: 30000,
  })
  return resp.data
}

async function refreshAccessToken(refreshToken) {
  const body = new URLSearchParams()
  body.set('grant_type', 'refresh_token')
  body.set('refresh_token', refreshToken)

  const resp = await axios.post(CANVA_TOKEN_URL, body.toString(), {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: basicAuthHeaderValue(),
    },
    timeout: 30000,
  })
  return resp.data
}

async function upsertConnectionForUser(userId, tokenPayload) {
  const accessToken = tokenPayload?.access_token || null
  const refreshToken = tokenPayload?.refresh_token || null
  const tokenType = tokenPayload?.token_type || 'bearer'
  const scopesRaw = tokenPayload?.scope || tokenPayload?.scopes || ''
  const scopes =
    typeof scopesRaw === 'string'
      ? scopesRaw
          .split(/\s+/)
          .map((s) => s.trim())
          .filter(Boolean)
      : Array.isArray(scopesRaw)
      ? scopesRaw
      : []

  const expiresIn = Number(tokenPayload?.expires_in || 0)
  const expiresAt = expiresIn ? new Date(Date.now() + expiresIn * 1000) : null

  const doc = await canvaDb.upsertConnectionForUser(userId, {
    accessTokenEnc: accessToken ? encryptString(accessToken) : null,
    refreshTokenEnc: refreshToken ? encryptString(refreshToken) : null,
    tokenType,
    scopes,
    expiresAt: expiresAt ? expiresAt.toISOString() : null,
  })
  return doc
}

async function getValidAccessTokenForUser(userId) {
  const conn = await canvaDb.getConnectionForUser(userId)
  if (!conn) {
    const err = new Error('Canva is not connected for this user')
    err.code = 'not_connected'
    throw err
  }

  const accessToken = decryptString(conn.accessTokenEnc)
  const refreshToken = decryptString(conn.refreshTokenEnc)

  const now = Date.now()
  const expiresAtMs = conn.expiresAt ? new Date(conn.expiresAt).getTime() : 0
  const needsRefresh =
    !accessToken || (expiresAtMs && expiresAtMs - now < 60 * 1000)

  if (!needsRefresh) return { accessToken, conn }

  if (!refreshToken) {
    const err = new Error('Canva token expired and no refresh token available')
    err.code = 'needs_reconnect'
    throw err
  }

  const refreshed = await refreshAccessToken(refreshToken)
  const updated = await upsertConnectionForUser(userId, {
    ...refreshed,
    // Some providers omit refresh_token on refresh; keep existing
    refresh_token: refreshed.refresh_token || refreshToken,
  })

  const nextAccess = decryptString(updated.accessTokenEnc)
  return {
    accessToken: nextAccess,
    conn: updated,
  }
}

async function canvaRequest(
  userId,
  method,
  path,
  { params, data, headers, responseType } = {},
) {
  const { accessToken } = await getValidAccessTokenForUser(userId)
  const url = `${CANVA_API_BASE}${path}`
  const resp = await axios.request({
    method,
    url,
    params,
    data,
    responseType: responseType || 'json',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(headers || {}),
    },
    timeout: 60000,
  })
  return resp.data
}

async function listBrandTemplates(userId, query = '') {
  return canvaRequest(userId, 'get', '/v1/brand-templates', {
    params: query ? { query } : undefined,
  })
}

async function getBrandTemplateDataset(userId, brandTemplateId) {
  return canvaRequest(
    userId,
    'get',
    `/v1/brand-templates/${encodeURIComponent(brandTemplateId)}/dataset`,
  )
}

async function createAutofillJob(userId, { brandTemplateId, title, data }) {
  return canvaRequest(userId, 'post', '/v1/autofills', {
    data: {
      brand_template_id: brandTemplateId,
      data,
      ...(title ? { title } : {}),
    },
  })
}

async function getAutofillJob(userId, jobId) {
  return canvaRequest(
    userId,
    'get',
    `/v1/autofills/${encodeURIComponent(jobId)}`,
  )
}

async function createExportJob(userId, { designId, format = 'pdf' }) {
  return canvaRequest(userId, 'post', '/v1/exports', {
    data: { design_id: designId, format },
  })
}

async function getExportJob(userId, exportId) {
  return canvaRequest(
    userId,
    'get',
    `/v1/exports/${encodeURIComponent(exportId)}`,
  )
}

async function createUrlAssetUploadJob(userId, { name, url }) {
  return canvaRequest(userId, 'post', '/v1/url-asset-uploads', {
    data: { name, url },
  })
}

async function getUrlAssetUploadJob(userId, jobId) {
  return canvaRequest(
    userId,
    'get',
    `/v1/url-asset-uploads/${encodeURIComponent(jobId)}`,
  )
}

async function createAssetUploadJob(userId, { name, bytes }) {
  // This endpoint uses application/octet-stream body and an Asset-Upload-Metadata header
  const { accessToken } = await getValidAccessTokenForUser(userId)
  const nameBase64 = Buffer.from(String(name || 'Asset'), 'utf8').toString(
    'base64',
  )
  const url = `${CANVA_API_BASE}/v1/asset-uploads`
  const resp = await axios.post(url, bytes, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/octet-stream',
      'Asset-Upload-Metadata': JSON.stringify({ name_base64: nameBase64 }),
    },
    timeout: 120000,
    maxBodyLength: Infinity,
  })
  return resp.data
}

async function getAssetUploadJob(userId, jobId) {
  return canvaRequest(
    userId,
    'get',
    `/v1/asset-uploads/${encodeURIComponent(jobId)}`,
  )
}

async function downloadUrl(url) {
  const resp = await axios.get(url, {
    responseType: 'arraybuffer',
    timeout: 120000,
  })
  return {
    data: resp.data,
    contentType: resp.headers['content-type'] || 'application/octet-stream',
  }
}

async function pollJob(fn, { intervalMs = 1500, timeoutMs = 90000 } = {}) {
  const start = Date.now()
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const res = await fn()
    const status = res?.job?.status
    if (status && status !== 'in_progress') return res
    if (Date.now() - start > timeoutMs) {
      const err = new Error('Timed out waiting for Canva job to complete')
      err.code = 'timeout'
      throw err
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}

module.exports = {
  generatePkcePair,
  buildAuthorizeUrl,
  exchangeCodeForToken,
  upsertConnectionForUser,
  getValidAccessTokenForUser,
  listBrandTemplates,
  getBrandTemplateDataset,
  createAutofillJob,
  getAutofillJob,
  createExportJob,
  getExportJob,
  createUrlAssetUploadJob,
  getUrlAssetUploadJob,
  createAssetUploadJob,
  getAssetUploadJob,
  pollJob,
  downloadUrl,
}
