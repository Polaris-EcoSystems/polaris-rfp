const express = require('express')
const cors = require('cors')
const helmet = require('helmet')
const morgan = require('morgan')
require('dotenv').config()

const rfpRoutes = require('./routes/rfp')
const attachmentRoutes = require('./routes/attachments')
const proposalRoutes = require('./routes/proposals')
const templateRoutes = require('./routes/templates')
const contentRoutes = require('./routes/content')
const aiRoutes = require('./routes/ai')
const authRoutes = require('./routes/auth')
const canvaRoutes = require('./routes/canva')

const app = express()
const PORT = process.env.PORT || 8080

// CORS allowlist
// - Local dev
// - Custom prod domain(s) (e.g. https://rfp.polariseco.com)
// - Amplify default domains / PR previews (e.g. https://main.<id>.amplifyapp.com)
// - Optional extra origins via env: FRONTEND_URL and/or FRONTEND_URLS (comma-separated)
const defaultAllowedOrigins = new Set([
  'http://localhost:3000',
  'http://localhost:3001',
  'http://localhost:3002',
  'https://rfp.polariseco.com',
])

for (const v of [process.env.FRONTEND_URL, process.env.FRONTEND_URLS]) {
  if (!v) continue
  for (const origin of String(v)
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)) {
    defaultAllowedOrigins.add(origin)
  }
}

function isAllowedOrigin(origin) {
  if (!origin) return true // curl/postman/health checks
  if (defaultAllowedOrigins.has(origin)) return true

  // Allow any Amplify default domain / preview domain
  // Examples:
  // - https://main.d3abcdefg.amplifyapp.com
  // - https://pr-123.d3abcdefg.amplifyapp.com
  try {
    const { hostname, protocol } = new URL(origin)
    if (protocol !== 'https:' && protocol !== 'http:') return false

    if (hostname.endsWith('.amplifyapp.com')) return true
    if (hostname === 'amplifyapp.com') return true

    // Allow any subdomain of polariseco.com (covers rfp, www, etc.)
    if (hostname === 'polariseco.com' || hostname.endsWith('.polariseco.com'))
      return true

    return false
  } catch {
    return false
  }
}

// Middleware
app.use(helmet())
app.use(
  cors({
    origin: (origin, cb) => {
      if (isAllowedOrigin(origin)) return cb(null, true)
      return cb(new Error(`CORS blocked origin: ${origin}`))
    },
    credentials: true,
    optionsSuccessStatus: 200,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With'],
  }),
)
app.use(morgan('combined'))
app.use(express.json({ limit: '10mb' }))
app.use(express.urlencoded({ extended: true, limit: '10mb' }))

// DynamoDB (required)
try {
  // will throw if not configured
  require('./db/ddb').getTableName()
  console.log('✅ DynamoDB configured via DDB_TABLE_NAME')
} catch (e) {
  console.error('❌ DynamoDB not configured:', e?.message || e)
}

// Routes
app.use('/api/rfp', rfpRoutes)
app.use('/api/rfp', attachmentRoutes)
app.use('/api/proposals', proposalRoutes)
app.use('/api/templates', templateRoutes)
app.use('/api/content', contentRoutes)
app.use('/api/ai', aiRoutes)
app.use('/api/auth', authRoutes)
app.use('/api/integrations/canva', canvaRoutes)

// Health check
app.get('/', (req, res) => {
  res.json({
    message: 'RFP Proposal Generation System API',
    version: '1.0.0',
    status: 'running',
    port: PORT,
    environment: process.env.NODE_ENV || 'development',
    dynamodb: process.env.DDB_TABLE_NAME ? 'configured' : 'missing',
    endpoints: [
      'GET /api/rfp',
      'POST /api/rfp',
      'GET /api/proposals',
      'POST /api/proposals',
      'GET /api/templates',
      'POST /api/templates',
      'GET /api/content',
      'POST /api/ai',
      'POST /api/auth/signup',
      'POST /api/auth/login',
    ],
  })
})

// Error handling middleware
app.use((err, req, res, next) => {
  console.error(err.stack)
  res.status(500).json({
    error: 'Something went wrong!',
    message:
      process.env.NODE_ENV === 'development'
        ? err.message
        : 'Internal server error',
  })
})

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({ error: 'Route not found' })
})

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running on port ${PORT}`)
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`)
  console.log(`Listening on 0.0.0.0:${PORT}`)
})
