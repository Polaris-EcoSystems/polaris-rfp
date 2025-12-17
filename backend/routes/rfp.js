const express = require('express')
const multer = require('multer')
const rfpAnalyzer = require('../services/rfpAnalyzer')
const SectionTitlesGenerator = require('../services/aiSectionsTitleGenerator')
const {
  createRfpFromAnalysis,
  getRfpById,
  listRfps,
  updateRfp,
  deleteRfp,
  listRfpProposalSummaries,
} = require('../db/rfps')

const router = express.Router()

// Configure multer for RFP file uploads (PDF only)
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 10 * 1024 * 1024, // 10MB limit
  },
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf') {
      cb(null, true)
    } else {
      cb(new Error('Only PDF files are allowed'))
    }
  },
})

// Analyze RFP from URL
router.post('/analyze-url', async (req, res) => {
  try {
    const { url } = req.body

    if (!url) {
      return res.status(400).json({ error: 'URL is required' })
    }

    console.log('Analyzing RFP from URL:', url)

    // Analyze the RFP from URL
    const analysis = await rfpAnalyzer.analyzeRFP(url, url)

    const saved = await createRfpFromAnalysis({
      analysis,
      sourceFileName: `URL_${Date.now()}`,
      sourceFileSize: 0,
    })
    console.log('RFP from URL saved successfully:', saved._id)
    res.status(201).json(saved)
  } catch (error) {
    console.error('RFP URL analysis error:', error)
    res.status(500).json({
      error: 'Failed to analyze RFP from URL',
      message: error.message,
    })
  }
})

// Analyze multiple RFP URLs (Finder MVP)
router.post('/analyze-urls', async (req, res) => {
  try {
    const urls = Array.isArray(req.body?.urls)
      ? req.body.urls.map((u) => String(u || '').trim()).filter(Boolean)
      : []
    if (urls.length === 0) {
      return res.status(400).json({ error: 'urls[] is required' })
    }

    const results = []
    for (const url of urls) {
      try {
        const analysis = await rfpAnalyzer.analyzeRFP(url, url)
        const saved = await createRfpFromAnalysis({
          analysis,
          sourceFileName: `URL_${Date.now()}`,
          sourceFileSize: 0,
        })
        results.push({ url, ok: true, rfp: saved })
      } catch (e) {
        results.push({
          url,
          ok: false,
          error: e?.message || 'Failed to analyze URL',
        })
      }
    }

    return res.status(201).json({ results })
  } catch (error) {
    console.error('RFP batch URL analysis error:', error)
    return res.status(500).json({
      error: 'Failed to analyze RFP URLs',
      message: error.message,
    })
  }
})

// Upload and analyze RFP
router.post('/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No file uploaded' })
    }

    console.log('Analyzing RFP:', req.file.originalname)

    // Analyze the RFP
    const analysis = await rfpAnalyzer.analyzeRFP(
      req.file.buffer,
      req.file.originalname,
    )
    const saved = await createRfpFromAnalysis({
      analysis,
      sourceFileName: req.file.originalname,
      sourceFileSize: req.file.size,
    })
    console.log('RFP saved successfully:', saved._id)
    res.status(201).json(saved)
  } catch (error) {
    console.error('RFP upload error:', error)
    res.status(500).json({
      error: 'Failed to process RFP',
      message: error.message,
    })
  }
})

// Get all RFPs
router.get('/', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1
    const limit = parseInt(req.query.limit) || 20
    const resp = await listRfps({ page, limit })
    res.json(resp)
  } catch (error) {
    console.error('Error fetching RFPs:', error)
    res.status(500).json({ error: 'Failed to fetch RFPs' })
  }
})

// Get single RFP
router.get('/:id', async (req, res) => {
  try {
    const rfp = await getRfpById(req.params.id)
    if (!rfp) return res.status(404).json({ error: 'RFP not found' })
    res.json(rfp)
  } catch (error) {
    console.error('Error fetching RFP:', error)
    res.status(500).json({ error: 'Failed to fetch RFP' })
  }
})

// Generate AI-driven proposal section titles (titles only)
router.post('/:id/ai-section-titles', async (req, res) => {
  try {
    const rfp = await getRfpById(req.params.id)
    if (!rfp) return res.status(404).json({ error: 'RFP not found' })
    if (Array.isArray(rfp.sectionTitles) && rfp.sectionTitles.length > 0) {
      return res.json({ titles: rfp.sectionTitles })
    }
    const titles = await SectionTitlesGenerator.generateSectionTitles(rfp)
    await updateRfp(req.params.id, { sectionTitles: titles })
    return res.json({ titles })
  } catch (error) {
    console.error('AI section titles error:', error)
    return res.status(500).json({
      error: 'Failed to generate section titles',
      message: error.message,
    })
  }
})

// Update RFP
router.put('/:id', async (req, res) => {
  try {
    const updated = await updateRfp(req.params.id, req.body || {})
    if (!updated) return res.status(404).json({ error: 'RFP not found' })
    res.json(updated)
  } catch (error) {
    console.error('Error updating RFP:', error)
    res.status(500).json({ error: 'Failed to update RFP' })
  }
})

// Get proposals for a specific RFP
router.get('/:id/proposals', async (req, res) => {
  try {
    const proposals = await listRfpProposalSummaries(req.params.id)
    res.json({ data: proposals })
  } catch (error) {
    console.error('Error fetching RFP proposals:', error)
    res.status(500).json({ error: 'Failed to fetch RFP proposals' })
  }
})

// Delete RFP
router.delete('/:id', async (req, res) => {
  try {
    await deleteRfp(req.params.id)
    res.json({ message: 'RFP deleted successfully' })
  } catch (error) {
    console.error('Error deleting RFP:', error)
    res.status(500).json({ error: 'Failed to delete RFP' })
  }
})

// Search RFPs
router.get('/search/:query', async (req, res) => {
  try {
    // Cheap search: fetch first page and filter in memory (good enough for now)
    const q = String(req.params.query || '').toLowerCase()
    const { data } = await listRfps({ page: 1, limit: 200 })
    const filtered = (data || []).filter((r) => {
      const hay = `${r.title || ''} ${r.clientName || ''} ${
        r.projectType || ''
      }`.toLowerCase()
      return hay.includes(q)
    })
    res.json(filtered.slice(0, 20))
  } catch (error) {
    console.error('Error searching RFPs:', error)
    res.status(500).json({ error: 'Search failed' })
  }
})

module.exports = router
