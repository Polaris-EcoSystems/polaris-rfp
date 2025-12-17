const express = require('express')
const PDFDocument = require('pdfkit')
const path = require('path')
const AIProposalGenerator = require('../services/aiProposalGenerator')
const TemplateGenerator = require('../services/templateGenerator')
const DocxGenerator = require('../services/docxGenerator')
const PdfGenerator = require('../services/pdfGenerator')
const { Packer } = require('docx')
const router = express.Router()
const { getRfpById } = require('../db/rfps')
const { getTemplateById } = require('../db/templates')
const {
  getBuiltinTemplate,
  toGeneratorTemplate,
} = require('../services/templatesCatalog')
const {
  createProposal,
  getProposalById,
  listProposals,
  updateProposal,
  deleteProposal,
  updateProposalReview,
} = require('../db/proposals')
const {
  getCompanyByCompanyId,
  listCompanies,
  getTeamMembersByIds,
  getProjectReferencesByIds,
} = require('../db/content')

// Generate new proposal with AI
router.post('/generate', async (req, res) => {
  try {
    const { rfpId, templateId, title, companyId, customContent = {} } = req.body

    // Validate required fields
    if (!rfpId || !templateId || !title) {
      return res.status(400).json({
        error: 'Missing required fields: rfpId, templateId, title',
      })
    }

    // Get RFP data
    const rfp = await getRfpById(rfpId)
    if (!rfp) {
      return res.status(404).json({ error: 'RFP not found' })
    }

    // Propagate selected companyId into customContent so generators can use it
    const effectiveCustomContent = {
      ...(customContent || {}),
      ...(companyId ? { companyId } : {}),
    }

    let sections

    // If templateId is a special AI flow, keep existing behavior using RFP-driven sections
    if (templateId === 'ai-template') {
      sections = await AIProposalGenerator.generateAIProposalSections(
        rfp,
        templateId,
        effectiveCustomContent,
      )
    } else {
      const builtin = getBuiltinTemplate(templateId)
      const template = builtin
        ? { ...builtin, isBuiltin: true }
        : await getTemplateById(templateId)
      if (!template)
        return res.status(404).json({ error: 'Template not found' })
      const genTemplate = toGeneratorTemplate(template)
      sections = await TemplateGenerator.generateAIProposalFromTemplate(
        rfp,
        genTemplate,
        effectiveCustomContent,
      )
    }

    const proposal = await createProposal({
      rfpId,
      companyId: companyId || null,
      templateId,
      title,
      sections,
      customContent: effectiveCustomContent,
      rfpSummary: {
        title: rfp.title,
        clientName: rfp.clientName,
        projectType: rfp.projectType,
      },
    })
    res.status(201).json(proposal)
  } catch (error) {
    console.error('Error generating proposal:', error)
    res.status(500).json({
      error: 'Failed to generate proposal',
      message: error.message,
    })
  }
})

// Generate proposal sections using AI
router.post('/:id/generate-sections', async (req, res) => {
  try {
    const proposal = await getProposalById(req.params.id, {
      includeSections: true,
    })

    if (!proposal) {
      return res.status(404).json({ error: 'Proposal not found' })
    }

    if (!AIProposalGenerator.openai) {
      return res.status(500).json({ error: 'OpenAI API key not configured' })
    }

    // Generate AI sections
    const sections = await AIProposalGenerator.generateAIProposalSections(
      await getRfpById(proposal.rfpId),
      proposal.templateId,
      {},
    )

    // Update proposal with new sections
    const updated = await updateProposal(req.params.id, {
      sections,
      lastModifiedBy: 'ai-generation',
    })

    res.json({
      message: 'Sections generated successfully',
      sections: sections,
      proposal: updated,
    })
  } catch (error) {
    console.error('Error generating AI sections:', error)
    res.status(500).json({
      error: 'Failed to generate AI sections',
      message: error.message,
    })
  }
})

// Get all proposals
router.get('/', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1
    const limit = parseInt(req.query.limit) || 20
    const resp = await listProposals({ page, limit })
    res.json(resp)
  } catch (error) {
    console.error('Error fetching proposals:', error)
    res.status(500).json({ error: 'Failed to fetch proposals' })
  }
})

// Get single proposal
router.get('/:id', async (req, res) => {
  try {
    const proposal = await getProposalById(req.params.id, {
      includeSections: true,
    })

    if (!proposal) {
      return res.status(404).json({ error: 'Proposal not found' })
    }

    res.json(proposal)
  } catch (error) {
    console.error('Error fetching proposal:', error)
    res.status(500).json({ error: 'Failed to fetch proposal' })
  }
})

// Update proposal
router.put('/:id', async (req, res) => {
  try {
    const updated = await updateProposal(req.params.id, {
      ...(req.body || {}),
      lastModifiedBy: 'system',
    })
    if (!updated) return res.status(404).json({ error: 'Proposal not found' })
    res.json(updated)
  } catch (error) {
    console.error('Error updating proposal:', error)
    res.status(500).json({ error: 'Failed to update proposal' })
  }
})

// Delete proposal
router.delete('/:id', async (req, res) => {
  try {
    await deleteProposal(req.params.id)
    res.json({ message: 'Proposal deleted successfully' })
  } catch (error) {
    console.error('Error deleting proposal:', error)
    res.status(500).json({ error: 'Failed to delete proposal' })
  }
})

// (Removed earlier duplicate export-pdf route that stripped bold formatting)

router.get('/:id/export-pdf', async (req, res) => {
  try {
    const proposal = await getProposalById(req.params.id, {
      includeSections: true,
    })

    if (!proposal) {
      return res.status(404).json({ error: 'Proposal not found' })
    }

    const rfp = await getRfpById(proposal.rfpId)
    const company = proposal.companyId
      ? await getCompanyByCompanyId(proposal.companyId)
      : (await listCompanies({ limit: 1 })).at(0)

    const hydratedProposal = {
      ...proposal,
      rfpId: rfp || proposal.rfpId,
    }

    // Set response headers
    res.setHeader('Content-Type', 'application/pdf')
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="${proposal.title.replace(/\s+/g, '_')}.pdf"`,
    )

    // Generate PDF using PdfGenerator service
    const pdfGenerator = new PdfGenerator()
    pdfGenerator.generatePdf(hydratedProposal, company || {}, res)
  } catch (error) {
    console.error('Error exporting proposal as PDF:', error)
    res.status(500).json({ error: 'Failed to export proposal PDF' })
  }
})

// Export proposal as DOCX
router.get('/:id/export-docx', async (req, res) => {
  console.log('🚀 Starting DOCX export request...')
  console.log('📋 Request params:', req.params)

  try {
    console.log('🔍 Looking up proposal with ID:', req.params.id)
    const proposal = await getProposalById(req.params.id, {
      includeSections: true,
    })

    if (!proposal) {
      console.error('❌ Proposal not found for ID:', req.params.id)
      return res.status(404).json({ error: 'Proposal not found' })
    }

    const rfp = await getRfpById(proposal.rfpId)
    const hydratedProposal = {
      ...proposal,
      rfpId: rfp || proposal.rfpId,
    }

    console.log('✅ Proposal found:', {
      id: hydratedProposal._id,
      title: proposal.title,
      hasRfpId: !!hydratedProposal.rfpId,
      rfpId: hydratedProposal.rfpId?._id || hydratedProposal.rfpId,
      sectionsCount: Object.keys(proposal.sections || {}).length,
    })

    console.log('🏢 Looking up company information...')
    const company = proposal.companyId
      ? (await getCompanyByCompanyId(proposal.companyId)) || {}
      : (await listCompanies({ limit: 1 })).at(0) || {}
    console.log('✅ Company data retrieved:', {
      hasCompany: !!company,
      companyId: company?._id,
      companyName: company?.name,
      companyKeys: company ? Object.keys(company) : [],
    })

    console.log('📄 Creating DocxGenerator instance...')
    const docxGenerator = new DocxGenerator() // <-- now uses officegen inside
    console.log('✅ DocxGenerator created')

    console.log('📝 Starting DOCX generation with officegen...')
    const buffer = await docxGenerator.generateDocx(hydratedProposal, company)
    console.log(
      '✅ DOCX document generated successfully, size:',
      buffer.length,
      'bytes',
    )

    // Ensure filename is safe
    const filename =
      (proposal.title || 'proposal')
        .replace(/\s+/g, '_')
        .replace(/[^a-zA-Z0-9_-]/g, '') + '.docx'
    console.log('📁 Generated filename:', filename)

    // Set headers before sending
    res.setHeader(
      'Content-Type',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`)

    console.log('📤 Sending DOCX buffer to response...')
    res.send(buffer)
    console.log('🎉 DOCX export completed successfully')
  } catch (error) {
    console.error('❌ Error exporting proposal as DOCX:', error)
    res.status(500).json({
      error: 'Failed to export proposal DOCX',
      message: error.message,
      details: process.env.NODE_ENV === 'development' ? error.stack : undefined,
    })
  }
})

// Update content library selection for a section
router.put('/:id/content-library/:sectionName', async (req, res) => {
  try {
    const { id, sectionName } = req.params
    const { selectedIds, type } = req.body // type: 'team', 'references', or 'company'

    const proposal = await getProposalById(id, { includeSections: true })
    if (!proposal) {
      return res.status(404).json({ error: 'Proposal not found' })
    }

    let content = ''

    if (type === 'company') {
      const SharedSectionFormatters = require('../services/sharedSectionFormatters')

      if (selectedIds.length > 0) {
        const selectedCompany = await getCompanyByCompanyId(selectedIds[0]) // Only use first selected company

        if (selectedCompany) {
          // Get RFP data from the proposal
          const rfp = await getRfpById(proposal.rfpId)

          // Determine section type based on section name
          const sectionTitle = sectionName.toLowerCase()
          if (sectionTitle === 'title') {
            // Title section returns an object, not a string
            const titleData = SharedSectionFormatters.formatTitleSection(
              selectedCompany,
              rfp || {},
            )
            content = titleData // Store the object directly
          } else if (
            sectionTitle.includes('cover letter') ||
            sectionTitle.includes('introduction letter') ||
            sectionTitle.includes('transmittal letter')
          ) {
            content = SharedSectionFormatters.formatCoverLetterSection(
              selectedCompany,
              rfp || {},
            )
          } else {
            // This is an experience/qualifications section
            content = await SharedSectionFormatters.formatExperienceSection(
              selectedCompany,
              rfp || {},
            )
          }
        } else {
          content = 'Selected company not found.'
        }
      } else {
        content = 'No company selected.'
      }
    } else if (type === 'team') {
      const selectedMembers = (await getTeamMembersByIds(selectedIds)).filter(
        (m) => m && (m.isActive === undefined || m.isActive === true),
      )
      const rfp = await getRfpById(proposal.rfpId)
      const projectType = rfp?.projectType || null

      if (selectedMembers.length > 0) {
        const {
          pickTeamMemberBio,
          pickTeamMemberExperience,
        } = require('../services/teamMemberProfiles')
        content =
          'Our experienced team brings together diverse expertise and proven track record to deliver exceptional results.\n\n'
        selectedMembers.forEach((member) => {
          const bio = pickTeamMemberBio(member, projectType)
          const exp = pickTeamMemberExperience(member, projectType)
          content += `**${member.nameWithCredentials}** - ${member.position}\n\n`
          if (bio) content += `${bio}\n\n`
          if (exp) content += `**Relevant experience:**\n\n${exp}\n\n`
        })
      } else {
        content = 'No team members selected.'
      }
    } else if (type === 'references') {
      const selectedReferences = (
        await getProjectReferencesByIds(selectedIds)
      ).filter(
        (r) =>
          r &&
          (r.isActive === undefined || r.isActive === true) &&
          (r.isPublic === undefined || r.isPublic === true),
      )

      if (selectedReferences.length > 0) {
        content =
          'Below are some of our recent project references that demonstrate our capabilities and client satisfaction:\n\n'
        selectedReferences.forEach((reference) => {
          content += `**${reference.organizationName}**`
          if (reference.timePeriod) {
            content += ` (${reference.timePeriod})`
          }
          content += '\n\n'

          content += `**Contact:** ${reference.contactName}`
          if (reference.contactTitle) {
            content += `, ${reference.contactTitle}`
          }
          if (reference.additionalTitle) {
            content += ` - ${reference.additionalTitle}`
          }
          content += ` of ${reference.organizationName}\n\n`

          if (reference.contactEmail) {
            content += `**Email:** ${reference.contactEmail}\n\n`
          }

          if (reference.contactPhone) {
            content += `**Phone:** ${reference.contactPhone}\n\n`
          }

          content += `**Scope of Work:** ${reference.scopeOfWork}\n\n`
          content += '---\n\n'
        })
      } else {
        content = 'No references selected.'
      }
    }

    // Update the section
    const updatedSections = {
      ...proposal.sections,
      [sectionName]: {
        ...proposal.sections[sectionName],
        content: typeof content === 'string' ? content.trim() : content,
        type: 'content-library',
        lastModified: new Date().toISOString(),
        selectedIds: selectedIds, // Store the selected IDs for future reference
      },
    }

    const updatedProposal = await updateProposal(id, {
      sections: updatedSections,
    })

    res.json(updatedProposal)
  } catch (error) {
    console.error('Error updating content library selection:', error)
    res
      .status(500)
      .json({ error: 'Failed to update content library selection' })
  }
})

// Switch proposal company (re-apply Title/Cover Letter/Experience)
router.put('/:id/company', async (req, res) => {
  try {
    const { id } = req.params
    const { companyId } = req.body || {}
    if (!companyId || typeof companyId !== 'string') {
      return res.status(400).json({ error: 'companyId is required' })
    }

    const proposal = await getProposalById(id, { includeSections: true })
    if (!proposal) return res.status(404).json({ error: 'Proposal not found' })

    const company = await getCompanyByCompanyId(companyId)
    if (!company) return res.status(404).json({ error: 'Company not found' })

    const rfp = await getRfpById(proposal.rfpId)
    const SharedSectionFormatters = require('../services/sharedSectionFormatters')

    const updatedSections = { ...(proposal.sections || {}) }

    // Update/insert Title
    updatedSections.Title = {
      ...(updatedSections.Title || {}),
      content: SharedSectionFormatters.formatTitleSection(company, rfp || {}),
      type: 'content-library',
      lastModified: new Date().toISOString(),
      selectedIds: [companyId],
    }

    // Update/insert Cover Letter
    updatedSections['Cover Letter'] = {
      ...(updatedSections['Cover Letter'] || {}),
      content: SharedSectionFormatters.formatCoverLetterSection(
        company,
        rfp || {},
      ),
      type: 'content-library',
      lastModified: new Date().toISOString(),
      selectedIds: [companyId],
    }

    // If there is an experience-like section already marked as content-library, refresh it.
    // Otherwise, if a common experience section exists, refresh it; else skip.
    const sectionNames = Object.keys(updatedSections)
    const experienceCandidates = sectionNames.filter((name) => {
      const n = String(name || '').toLowerCase()
      return (
        n.includes('experience') ||
        n.includes('qualifications') ||
        n.includes('firm') ||
        n.includes('capabilities') ||
        n.includes('company profile')
      )
    })
    for (const name of experienceCandidates.slice(0, 2)) {
      // Update only if the section is content-library or looks like a firm quals section
      updatedSections[name] = {
        ...(updatedSections[name] || {}),
        content: await SharedSectionFormatters.formatExperienceSection(
          company,
          rfp || {},
        ),
        type: 'content-library',
        lastModified: new Date().toISOString(),
        selectedIds: [companyId],
      }
    }

    const updated = await updateProposal(id, {
      companyId,
      customContent: { ...(proposal.customContent || {}), companyId },
      sections: updatedSections,
      lastModifiedBy: 'system',
    })
    return res.json(updated)
  } catch (error) {
    console.error('Error switching proposal company:', error)
    return res.status(500).json({ error: 'Failed to switch proposal company' })
  }
})

// Update proposal review (score/notes/rubric)
router.put('/:id/review', async (req, res) => {
  try {
    const { id } = req.params
    const { score, notes, rubric, decision } = req.body || {}

    const proposal = await getProposalById(id, { includeSections: true })
    if (!proposal) return res.status(404).json({ error: 'Proposal not found' })

    let nextScore = null
    if (score !== undefined && score !== null && score !== '') {
      const n = Number(score)
      if (Number.isFinite(n)) nextScore = Math.max(0, Math.min(100, n))
    }

    let nextDecision = proposal.review?.decision || ''
    if (decision === null) nextDecision = ''
    if (typeof decision === 'string') {
      const d = decision.trim().toLowerCase()
      if (d === '' || d === 'shortlist' || d === 'reject') nextDecision = d
    }

    const nextReview = {
      ...(proposal.review || {}),
      score: nextScore,
      decision: nextDecision,
      notes: typeof notes === 'string' ? notes : proposal.review?.notes || '',
      rubric:
        rubric && typeof rubric === 'object'
          ? rubric
          : proposal.review?.rubric || {},
      updatedAt: new Date().toISOString(),
    }

    const updated = await updateProposalReview(id, nextReview)
    return res.json(updated)
  } catch (error) {
    console.error('Error updating proposal review:', error)
    return res.status(500).json({ error: 'Failed to update proposal review' })
  }
})

module.exports = router
