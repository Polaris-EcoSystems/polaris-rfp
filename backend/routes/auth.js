const express = require('express')
const { body, validationResult } = require('express-validator')
const { authMiddleware } = require('../middleware/auth')
const { createUser, verifyLogin } = require('../db/users')

const router = express.Router()

// Login
router.post(
  '/login',
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

module.exports = router
