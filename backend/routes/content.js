const express = require('express')

const {
  getCompanyByCompanyId,
  listCompanies,
  upsertCompany,
  deleteCompany,
  listTeamMembers,
  getTeamMemberById,
  upsertTeamMember,
  deleteTeamMember,
  listPastProjects,
  getPastProjectById,
  upsertPastProject,
  deletePastProject,
  listProjectReferences,
  upsertProjectReference,
  deleteProjectReference,
} = require('../db/content')

const router = express.Router()

// Helper function to replace company names
function replaceCompanyName(text, targetCompanyName) {
  if (!text || typeof text !== 'string' || !targetCompanyName) return text
  const companyNames = ['Eighth Generation Consulting', 'Polaris EcoSystems']
  let result = text
  companyNames.forEach((name) => {
    if (name !== targetCompanyName) {
      const regex = new RegExp(name, 'gi')
      result = result.replace(regex, targetCompanyName)
    }
  })
  return result
}

// Helper function to replace website URLs
function replaceWebsite(text, targetCompanyName) {
  if (!text || typeof text !== 'string' || !targetCompanyName) return text
  const websiteMap = {
    'Eighth Generation Consulting': 'https://eighthgen.com',
    'Polaris EcoSystems': 'https://polariseco.com',
  }
  const targetWebsite = websiteMap[targetCompanyName]
  if (!targetWebsite) return text

  const websites = Object.values(websiteMap)
  let result = text
  websites.forEach((website) => {
    if (website !== targetWebsite) {
      const withProtocol = new RegExp(
        website.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
        'gi',
      )
      const withoutProtocol = new RegExp(
        website.replace('https://', '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
        'gi',
      )
      result = result.replace(withProtocol, targetWebsite)
      result = result.replace(
        withoutProtocol,
        targetWebsite.replace('https://', ''),
      )
    }
  })
  return result
}

function getCompanyWebsite(companyName) {
  const websiteMap = {
    'Eighth Generation Consulting': 'https://eighthgen.com',
    'Polaris EcoSystems': 'https://polariseco.com',
  }
  return websiteMap[companyName] || null
}

function applyCompanyReplacements(company) {
  if (!company) return company
  const companyObj = { ...company }

  const textFields = [
    'description',
    'tagline',
    'missionStatement',
    'visionStatement',
    'coverLetter',
    'firmQualificationsAndExperience',
  ]

  textFields.forEach((field) => {
    if (companyObj[field] && typeof companyObj[field] === 'string') {
      companyObj[field] = replaceCompanyName(companyObj[field], companyObj.name)
      companyObj[field] = replaceWebsite(companyObj[field], companyObj.name)
    }
  })

  if (companyObj.values && Array.isArray(companyObj.values)) {
    companyObj.values = companyObj.values.map((value) => {
      let replaced = replaceCompanyName(value, companyObj.name)
      replaced = replaceWebsite(replaced, companyObj.name)
      return replaced
    })
  }

  if (companyObj.website) {
    companyObj.website =
      getCompanyWebsite(companyObj.name) || companyObj.website
  }

  return companyObj
}

// --- Companies ---

router.get('/companies', async (req, res) => {
  try {
    const companies = await listCompanies({ limit: 200 })
    res.json(companies.map(applyCompanyReplacements))
  } catch (error) {
    console.error('Error fetching companies:', error)
    res.status(500).json({ error: 'Failed to fetch companies' })
  }
})

// Get latest company or specific company
router.get('/company', async (req, res) => {
  try {
    const companyId = req.query.companyId ? String(req.query.companyId) : null
    if (companyId) {
      const c = await getCompanyByCompanyId(companyId)
      if (!c) return res.status(404).json({ error: 'Company not found' })
      return res.json(applyCompanyReplacements(c))
    }

    const latest = (await listCompanies({ limit: 1 })).at(0)
    return res.json(latest ? applyCompanyReplacements(latest) : null)
  } catch (error) {
    console.error('Error fetching company:', error)
    res.status(500).json({ error: 'Failed to fetch company' })
  }
})

router.get('/companies/:companyId', async (req, res) => {
  try {
    const company = await getCompanyByCompanyId(req.params.companyId)
    if (!company) return res.status(404).json({ error: 'Company not found' })
    res.json(applyCompanyReplacements(company))
  } catch (error) {
    console.error('Error fetching company:', error)
    res.status(500).json({ error: 'Failed to fetch company' })
  }
})

router.post('/companies', async (req, res) => {
  try {
    const {
      name,
      tagline,
      description,
      founded,
      location,
      website,
      email,
      phone,
      coreCapabilities,
      certifications,
      industryFocus,
      missionStatement,
      visionStatement,
      values,
      statistics,
      socialMedia,
      coverLetter,
      firmQualificationsAndExperience,
      sharedInfo,
    } = req.body || {}

    if (!name || !description) {
      return res
        .status(400)
        .json({ error: 'name and description are required' })
    }

    const created = await upsertCompany({
      companyId: req.body?.companyId,
      name,
      tagline,
      description,
      founded: founded || null,
      location,
      website,
      email,
      phone,
      coreCapabilities,
      certifications,
      industryFocus,
      missionStatement,
      visionStatement,
      values,
      statistics,
      socialMedia,
      coverLetter,
      firmQualificationsAndExperience,
      lastUpdated: new Date().toISOString(),
      sharedInfo: sharedInfo || null,
      isActive: true,
    })

    res.status(201).json(applyCompanyReplacements(created))
  } catch (error) {
    console.error('Error creating company:', error)
    res.status(500).json({ error: 'Failed to create company' })
  }
})

router.put('/companies/:companyId', async (req, res) => {
  try {
    const existing = await getCompanyByCompanyId(req.params.companyId)
    if (!existing) return res.status(404).json({ error: 'Company not found' })

    const updates = { ...req.body }
    updates.companyId = req.params.companyId
    updates.lastUpdated = new Date().toISOString()

    const updated = await upsertCompany({ ...existing, ...updates })
    res.json({
      company: applyCompanyReplacements(updated),
      affectedCompanies: [applyCompanyReplacements(updated)],
    })
  } catch (error) {
    console.error('Error updating company:', error)
    res.status(500).json({ error: 'Failed to update company' })
  }
})

router.delete('/companies/:companyId', async (req, res) => {
  try {
    const existing = await getCompanyByCompanyId(req.params.companyId)
    if (!existing) return res.status(404).json({ error: 'Company not found' })

    // soft-delete
    await upsertCompany({ ...existing, isActive: false })
    res.json({ success: true })
  } catch (error) {
    console.error('Error deleting company:', error)
    res.status(500).json({ error: 'Failed to delete company' })
  }
})

// Back-compat endpoint used by some UI
router.put('/company', async (req, res) => {
  try {
    const companyId = req.body?.companyId
    if (!companyId)
      return res.status(400).json({ error: 'companyId is required' })
    const existing = await getCompanyByCompanyId(companyId)
    if (!existing) return res.status(404).json({ error: 'Company not found' })

    const updated = await upsertCompany({
      ...existing,
      ...req.body,
      companyId,
      lastUpdated: new Date().toISOString(),
    })
    res.json(applyCompanyReplacements(updated))
  } catch (error) {
    console.error('Error updating company:', error)
    res.status(500).json({ error: 'Failed to update company' })
  }
})

// --- Team members ---

router.get('/team', async (req, res) => {
  try {
    const members = await listTeamMembers({ limit: 500 })
    res.json(
      members.filter(
        (m) => m && (m.isActive === undefined || m.isActive === true),
      ),
    )
  } catch (error) {
    console.error('Error fetching team members:', error)
    res.status(500).json({ error: 'Failed to fetch team members' })
  }
})

router.post('/team', async (req, res) => {
  try {
    const created = await upsertTeamMember({ ...req.body, isActive: true })
    res.status(201).json(created)
  } catch (error) {
    console.error('Error creating team member:', error)
    res.status(500).json({ error: 'Failed to create team member' })
  }
})

router.get('/team/:memberId', async (req, res) => {
  try {
    const member = await getTeamMemberById(req.params.memberId)
    if (!member) return res.status(404).json({ error: 'Team member not found' })
    res.json(member)
  } catch (error) {
    console.error('Error fetching team member:', error)
    res.status(500).json({ error: 'Failed to fetch team member' })
  }
})

router.put('/team/:memberId', async (req, res) => {
  try {
    const existing = await getTeamMemberById(req.params.memberId)
    if (!existing)
      return res.status(404).json({ error: 'Team member not found' })
    const updated = await upsertTeamMember({
      ...existing,
      ...req.body,
      memberId: req.params.memberId,
    })
    res.json(updated)
  } catch (error) {
    console.error('Error updating team member:', error)
    res.status(500).json({ error: 'Failed to update team member' })
  }
})

router.delete('/team/:memberId', async (req, res) => {
  try {
    const existing = await getTeamMemberById(req.params.memberId)
    if (!existing)
      return res.status(404).json({ error: 'Team member not found' })
    await upsertTeamMember({
      ...existing,
      isActive: false,
      memberId: req.params.memberId,
    })
    res.json({ success: true })
  } catch (error) {
    console.error('Error deleting team member:', error)
    res.status(500).json({ error: 'Failed to delete team member' })
  }
})

// --- Past projects ---

router.get('/projects', async (req, res) => {
  try {
    const { project_type, industry, count = 20 } = req.query
    const projects = await listPastProjects({
      limit: Math.min(500, parseInt(count) || 20),
    })
    const filtered = projects
      .filter((p) => p && (p.isActive === undefined || p.isActive === true))
      .filter((p) => (p.isPublic === undefined ? true : !!p.isPublic))
      .filter((p) =>
        project_type ? String(p.projectType) === String(project_type) : true,
      )
      .filter((p) =>
        industry ? String(p.industry) === String(industry) : true,
      )
      .slice(0, parseInt(count) || 20)

    res.json(filtered)
  } catch (error) {
    console.error('Error fetching projects:', error)
    res.status(500).json({ error: 'Failed to fetch projects' })
  }
})

router.post('/projects', async (req, res) => {
  try {
    const { title, clientName, description, industry, projectType, duration } =
      req.body || {}

    if (
      !title ||
      !clientName ||
      !description ||
      !industry ||
      !projectType ||
      !duration
    ) {
      return res.status(400).json({ error: 'Missing required fields' })
    }

    const created = await upsertPastProject({
      ...req.body,
      isActive: true,
      isPublic: req.body?.isPublic !== false,
    })

    res.status(201).json(created)
  } catch (error) {
    console.error('Error creating project:', error)
    res.status(500).json({ error: 'Failed to create project' })
  }
})

router.put('/projects/:id', async (req, res) => {
  try {
    const existing = await getPastProjectById(req.params.id)
    if (!existing) return res.status(404).json({ error: 'Project not found' })
    const updated = await upsertPastProject({
      ...existing,
      ...req.body,
      projectId: req.params.id,
    })
    res.json(updated)
  } catch (error) {
    console.error('Error updating project:', error)
    res.status(500).json({ error: 'Failed to update project' })
  }
})

router.delete('/projects/:id', async (req, res) => {
  try {
    const existing = await getPastProjectById(req.params.id)
    if (!existing) return res.status(404).json({ error: 'Project not found' })
    await upsertPastProject({
      ...existing,
      isActive: false,
      projectId: req.params.id,
    })
    res.json({ success: true })
  } catch (error) {
    console.error('Error deleting project:', error)
    res.status(500).json({ error: 'Failed to delete project' })
  }
})

// --- References ---

router.get('/references', async (req, res) => {
  try {
    const { project_type, count = 10 } = req.query
    const references = await listProjectReferences({ limit: 500 })
    const filtered = references
      .filter((r) => r && (r.isActive === undefined || r.isActive === true))
      .filter((r) => (r.isPublic === undefined ? true : !!r.isPublic))
      .filter((r) =>
        project_type ? String(r.projectType) === String(project_type) : true,
      )
      .slice(0, parseInt(count) || 10)

    res.json(filtered)
  } catch (error) {
    console.error('Error fetching references:', error)
    res.status(500).json({ error: 'Failed to fetch references' })
  }
})

router.post('/references', async (req, res) => {
  try {
    const { organizationName, contactName, contactEmail, scopeOfWork } =
      req.body || {}
    if (!organizationName || !contactName || !contactEmail || !scopeOfWork) {
      return res.status(400).json({ error: 'Missing required fields' })
    }

    const created = await upsertProjectReference({
      ...req.body,
      isPublic: Boolean(req.body?.isPublic !== false),
      isActive: true,
    })

    res.status(201).json(created)
  } catch (error) {
    console.error('Error creating reference:', error)
    res.status(500).json({ error: 'Failed to create reference' })
  }
})

router.put('/references/:id', async (req, res) => {
  try {
    const existing = await upsertProjectReference({
      ...req.body,
      referenceId: req.params.id,
      isActive: req.body?.isActive !== false,
    })
    res.json(existing)
  } catch (error) {
    console.error('Error updating reference:', error)
    res.status(500).json({ error: 'Failed to update reference' })
  }
})

router.delete('/references/:id', async (req, res) => {
  try {
    // soft-delete by overwriting isActive false if it exists, else hard delete
    const refs = await listProjectReferences({ limit: 500 })
    const existing = refs.find(
      (r) => String(r._id || r.referenceId) === String(req.params.id),
    )
    if (!existing) return res.status(404).json({ error: 'Reference not found' })
    await upsertProjectReference({
      ...existing,
      referenceId: req.params.id,
      isActive: false,
    })
    res.json({ success: true })
  } catch (error) {
    console.error('Error deleting reference:', error)
    res.status(500).json({ error: 'Failed to delete reference' })
  }
})

module.exports = router
