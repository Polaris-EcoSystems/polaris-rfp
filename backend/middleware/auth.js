const jwt = require('jsonwebtoken')
const { getUserById } = require('../db/users')
const { getJwtSecret } = require('../utils/jwtConfig')

const authMiddleware = async (req, res, next) => {
  try {
    const token = req.header('Authorization')?.replace('Bearer ', '')

    if (!token) {
      return res
        .status(401)
        .json({ error: 'Access denied. No token provided.' })
    }

    const decoded = jwt.verify(token, getJwtSecret())
    const user = await getUserById(decoded.userId)

    if (!user) {
      return res.status(401).json({ error: 'Invalid token.' })
    }

    if (!user.isActive) {
      return res.status(401).json({ error: 'Account is inactive.' })
    }

    // Match previous shape used by routes
    req.user = {
      _id: user.userId,
      username: user.username,
      email: user.email,
      role: user.role,
      isActive: user.isActive,
    }
    next()
  } catch (error) {
    res.status(401).json({ error: 'Invalid token.' })
  }
}

// No admin middleware: app supports only regular user authentication
module.exports = { authMiddleware }

// --- Authorization helpers (RBAC) ---
// Usage: router.get('/admin', authMiddleware, requireRole('admin'), handler)
function requireRole(...allowed) {
  const allow = new Set(
    allowed
      .flat()
      .filter(Boolean)
      .map((r) => String(r).toLowerCase()),
  )

  return (req, res, next) => {
    const role = String(req.user?.role || '').toLowerCase()
    if (allow.size === 0) return next()
    if (!role) return res.status(403).json({ error: 'Forbidden' })
    if (!allow.has(role)) return res.status(403).json({ error: 'Forbidden' })
    return next()
  }
}

module.exports.requireRole = requireRole
