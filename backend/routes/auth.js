const express = require('express')
const { body, validationResult } = require('express-validator')
const { authMiddleware } = require('../middleware/auth')
const { authLimiter, loginLimiter } = require('../middleware/rateLimit')
const { sendPasswordResetEmail } = require('../services/email')
const {
  createUser,
  verifyLogin,
  requestPasswordReset,
  resetPasswordWithToken,
} = require('../db/users')

const router = express.Router()

// Login
router.post(
  '/login',
  loginLimiter,
  [
    body('username').notEmpty().withMessage('Username is required'),
    body('password')
      .isLength({ min: 6 })
      .withMessage('Password must be at least 6 characters'),
  ],
  async (req, res) => {
    try {
      const errors = validationResult(req)
      if (!errors.isEmpty()) {
        return res.status(400).json({ errors: errors.array() })
      }

      const { username, password } = req.body

      const result = await verifyLogin({ usernameOrEmail: username, password })
      if (!result) {
        return res.status(401).json({ error: 'Invalid credentials' })
      }

      res.json({
        access_token: result.token,
        token_type: 'bearer',
        expires_in: process.env.JWT_EXPIRE || '24h',
      })
    } catch (error) {
      console.error('Login error:', error)
      res.status(500).json({ error: 'Login failed' })
    }
  },
)

// Get current user
router.get('/me', authMiddleware, async (req, res) => {
  try {
    res.json({
      username: req.user.username,
      email: req.user.email,
      role: req.user.role,
    })
  } catch (error) {
    res.status(500).json({ error: 'Failed to get user info' })
  }
})

// Public signup (open to all users)
router.post(
  '/signup',
  authLimiter,
  [
    body('username')
      .isLength({ min: 3 })
      .withMessage('Username must be at least 3 characters'),
    body('email').isEmail().withMessage('Valid email is required'),
    body('password')
      .isLength({ min: 6 })
      .withMessage('Password must be at least 6 characters'),
  ],
  async (req, res) => {
    try {
      if (
        process.env.NODE_ENV === 'production' &&
        String(process.env.DISABLE_PUBLIC_SIGNUP || '')
          .trim()
          .toLowerCase() === 'true'
      ) {
        return res.status(403).json({ error: 'Signup is disabled' })
      }

      const errors = validationResult(req)
      if (!errors.isEmpty()) {
        return res.status(400).json({ errors: errors.array() })
      }

      const { username, email, password } = req.body
      const created = await createUser({ username, email, password })

      res.status(201).json({
        message: 'User created successfully',
        access_token: created.token,
        token_type: 'bearer',
        expires_in: process.env.JWT_EXPIRE || '24h',
        user: {
          username: created.user.username,
          email: created.user.email,
        },
      })
    } catch (error) {
      console.error('Registration error:', error)
      if (error && error.code === 'user_exists') {
        return res.status(400).json({ error: 'User already exists' })
      }
      res.status(500).json({ error: 'Registration failed' })
    }
  },
)

// Request password reset (always returns 200 to avoid user enumeration)
router.post(
  '/request-password-reset',
  authLimiter,
  [body('email').isEmail().withMessage('Valid email is required')],
  async (req, res) => {
    const errors = validationResult(req)
    if (!errors.isEmpty()) {
      return res.status(400).json({ errors: errors.array() })
    }

    try {
      const { email } = req.body
      const result = await requestPasswordReset({ email })

      // In production we never reveal whether the email exists or the token.
      if (process.env.NODE_ENV === 'production') {
        // If a token was generated, email the reset link (best-effort).
        try {
          if (result?.token) {
            const frontendBase =
              process.env.FRONTEND_BASE_URL ||
              process.env.NEXT_PUBLIC_FRONTEND_BASE_URL ||
              'https://rfp.polariseco.com'
            const resetUrl = `${frontendBase}/reset-password/${result.token}`
            await sendPasswordResetEmail({ to: email, resetUrl })
          }
        } catch (e) {
          console.error('Password reset email send failed:', e?.message || e)
        }
        return res.json({ ok: true })
      }

      const frontendBase =
        process.env.FRONTEND_BASE_URL ||
        process.env.NEXT_PUBLIC_FRONTEND_BASE_URL ||
        'http://localhost:3000'
      const resetUrl = result?.token
        ? `${frontendBase}/reset-password/${result.token}`
        : null

      // In dev, also try to send email (best-effort) and return resetUrl for convenience.
      try {
        if (resetUrl) await sendPasswordResetEmail({ to: email, resetUrl })
      } catch (e) {
        console.error('Password reset email send failed:', e?.message || e)
      }

      return res.json({ ok: true, resetUrl })
    } catch (e) {
      // Still avoid enumeration/leaks
      return res.json({ ok: true })
    }
  },
)

// Complete password reset
router.post(
  '/reset-password',
  authLimiter,
  [
    body('token').notEmpty().withMessage('Token is required'),
    body('password')
      .isLength({ min: 8 })
      .withMessage('Password must be at least 8 characters'),
  ],
  async (req, res) => {
    const errors = validationResult(req)
    if (!errors.isEmpty()) {
      return res.status(400).json({ errors: errors.array() })
    }

    try {
      const { token, password } = req.body
      const result = await resetPasswordWithToken({
        token,
        newPassword: password,
      })
      return res.json({
        ok: true,
        access_token: result.token,
        token_type: 'bearer',
        expires_in: process.env.JWT_EXPIRE || '24h',
      })
    } catch (e) {
      return res.status(400).json({ error: 'Invalid or expired reset token' })
    }
  },
)

module.exports = router
