const express = require('express')
const multer = require('multer')
const path = require('path')
const fs = require('fs')
const pdf = require('pdf-parse')
const mammoth = require('mammoth')
const { getRfpById } = require('../db/rfps')
const {
  addAttachments,
  listAttachments,
  getAttachment,
  deleteAttachment,
} = require('../db/attachments')

const router = express.Router()

// Ensure attachments directory exists
const attachmentsDir = path.join(__dirname, '../uploads/attachments')
if (!fs.existsSync(attachmentsDir)) {
  fs.mkdirSync(attachmentsDir, { recursive: true })
}

// Configure multer for attachments (multiple file types)
const attachmentStorage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, attachmentsDir)
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1e9)
    const ext = path.extname(file.originalname)
    cb(null, uniqueSuffix + ext)
  },
})

const attachmentUpload = multer({
  storage: attachmentStorage,
  limits: {
    fileSize: 50 * 1024 * 1024, // 50MB limit for attachments
  },
  fileFilter: (req, file, cb) => {
    // Allow common file types
    const allowedMimeTypes = [
      'application/pdf',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'text/plain',
      'image/jpeg',
      'image/png',
      'image/gif',
      'image/webp',
      'application/zip',
      'application/x-zip-compressed',
    ]

    if (allowedMimeTypes.includes(file.mimetype)) {
      cb(null, true)
    } else {
      cb(new Error(`File type ${file.mimetype} is not allowed`))
    }
  },
})

// Helper function to determine file type category
const getFileTypeCategory = (mimeType) => {
  if (mimeType.startsWith('image/')) return 'image'
  if (mimeType === 'application/pdf') return 'pdf'
  if (
    mimeType === 'application/msword' ||
    mimeType ===
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  )
    return 'doc'
  if (
    mimeType === 'application/vnd.ms-excel' ||
    mimeType ===
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  )
    return 'excel'
  if (mimeType === 'text/plain') return 'txt'
  if (mimeType.includes('zip')) return 'zip'
  return 'other'
}

// Helper function to extract text content from files
const extractTextContent = async (filePath, mimeType) => {
  try {
    // Extract text from PDF
    if (mimeType === 'application/pdf') {
      const dataBuffer = fs.readFileSync(filePath)
      const pdfData = await pdf(dataBuffer)
      return pdfData.text
    }

    // Extract text from DOCX
    if (
      mimeType ===
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ) {
      const result = await mammoth.extractRawText({ path: filePath })
      return result.value
    }

    // Extract text from plain text files
    if (mimeType === 'text/plain') {
      return fs.readFileSync(filePath, 'utf-8')
    }

    // For other file types, return null
    return null
  } catch (error) {
    console.error('Error extracting text from file:', error)
    return null
  }
}

// Upload attachments to an RFP
router.post(
  '/:id/upload-attachments',
  attachmentUpload.array('files', 10),
  async (req, res) => {
    try {
      const rfp = await getRfpById(req.params.id)

      if (!rfp) {
        // Clean up uploaded files if RFP not found
        if (req.files) {
          req.files.forEach((file) => {
            fs.unlink(file.path, (err) => {
              if (err) console.error('Error deleting file:', err)
            })
          })
        }
        return res.status(404).json({ error: 'RFP not found' })
      }

      if (!req.files || req.files.length === 0) {
        return res.status(400).json({ error: 'No files uploaded' })
      }

      // Process each uploaded file and extract text content
      const attachmentPayloads = await Promise.all(
        req.files.map(async (file) => {
          const textContent = await extractTextContent(file.path, file.mimetype)

          return {
            fileName: file.filename,
            originalName: file.originalname,
            fileSize: file.size,
            mimeType: file.mimetype,
            fileType: getFileTypeCategory(file.mimetype),
            filePath: file.path,
            description: req.body.description || '',
            textContent: textContent,
            textLength: textContent ? textContent.length : 0,
          }
        }),
      )

      const attachments = await addAttachments(
        req.params.id,
        attachmentPayloads,
      )

      res.json({
        message: `${attachments.length} file(s) uploaded successfully`,
        attachments: attachments.map((att) => ({
          id: att.id,
          fileName: att.fileName,
          originalName: att.originalName,
          fileSize: att.fileSize,
          fileType: att.fileType,
          uploadedAt: att.uploadedAt,
          description: att.description,
        })),
      })
    } catch (error) {
      console.error('Error uploading attachments:', error)
      // Clean up uploaded files on error
      if (req.files) {
        req.files.forEach((file) => {
          fs.unlink(file.path, (err) => {
            if (err) console.error('Error deleting file:', err)
          })
        })
      }
      res.status(500).json({ error: 'Failed to upload attachments' })
    }
  },
)

// Get all attachments for an RFP
router.get('/:id/attachments', async (req, res) => {
  try {
    const rfp = await getRfpById(req.params.id)
    if (!rfp) return res.status(404).json({ error: 'RFP not found' })

    const attachments = await listAttachments(req.params.id)
    res.json({
      attachments: attachments.map((att) => ({
        id: att.id,
        originalName: att.originalName,
        fileSize: att.fileSize,
        fileType: att.fileType,
        mimeType: att.mimeType,
        uploadedAt: att.uploadedAt,
        description: att.description,
      })),
    })
  } catch (error) {
    console.error('Error fetching attachments:', error)
    res.status(500).json({ error: 'Failed to fetch attachments' })
  }
})

// Download a specific attachment
router.get('/:id/attachments/:attachmentId', async (req, res) => {
  try {
    const rfp = await getRfpById(req.params.id)
    if (!rfp) return res.status(404).json({ error: 'RFP not found' })

    const attachment = await getAttachment(
      req.params.id,
      req.params.attachmentId,
    )

    if (!attachment) {
      return res.status(404).json({ error: 'Attachment not found' })
    }

    // Check if file exists
    if (!fs.existsSync(attachment.filePath)) {
      return res.status(404).json({ error: 'File not found on server' })
    }

    // Set headers for file download
    res.setHeader('Content-Type', attachment.mimeType)
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="${attachment.originalName}"`,
    )

    // Stream file to response
    const fileStream = fs.createReadStream(attachment.filePath)
    fileStream.pipe(res)
  } catch (error) {
    console.error('Error downloading attachment:', error)
    res.status(500).json({ error: 'Failed to download attachment' })
  }
})

// Delete a specific attachment
router.delete('/:id/attachments/:attachmentId', async (req, res) => {
  try {
    const rfp = await getRfpById(req.params.id)
    if (!rfp) return res.status(404).json({ error: 'RFP not found' })

    const attachment = await getAttachment(
      req.params.id,
      req.params.attachmentId,
    )

    if (!attachment) {
      return res.status(404).json({ error: 'Attachment not found' })
    }

    const filePath = attachment.filePath

    await deleteAttachment(req.params.id, req.params.attachmentId)

    // Delete file from disk
    if (fs.existsSync(filePath)) {
      fs.unlink(filePath, (err) => {
        if (err) console.error('Error deleting file:', err)
      })
    }

    res.json({ message: 'Attachment deleted successfully' })
  } catch (error) {
    console.error('Error deleting attachment:', error)
    res.status(500).json({ error: 'Failed to delete attachment' })
  }
})

module.exports = router
