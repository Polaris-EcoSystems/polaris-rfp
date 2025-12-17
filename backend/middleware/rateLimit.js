const rateLimit = require('express-rate-limit')

function minutes(n) {
  return n * 60 * 1000
}

// Note: This uses the default in-memory store.
// It is still valuable, but for multi-instance production you’d typically use Redis/etc.
const authLimiter = rateLimit({
  windowMs: minutes(15),
  max: 30,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many requests. Please try again later.' },
})

const loginLimiter = rateLimit({
  windowMs: minutes(15),
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many login attempts. Please try again later.' },
})

module.exports = { authLimiter, loginLimiter }
