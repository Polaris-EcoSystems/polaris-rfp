function getJwtSecret() {
  const secret = String(process.env.JWT_SECRET || '').trim()

  // Dev fallback is convenient locally, but is unsafe for production.
  if (!secret || secret === 'your-secret-key') {
    if (process.env.NODE_ENV === 'production') {
      throw new Error(
        'JWT_SECRET must be set to a strong secret in production (do not use the default).',
      )
    }
    return secret || 'your-secret-key'
  }

  return secret
}

function getJwtExpire() {
  return process.env.JWT_EXPIRE || '24h'
}

module.exports = { getJwtSecret, getJwtExpire }
