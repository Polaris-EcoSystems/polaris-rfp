const express = require('express')

const { authMiddleware } = require('../middleware/auth')
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
  getProjectReferenceById,
  upsertProjectReference,
  deleteProjectReference,
} = require('../db/content')

const {
  getAssetsBucketName,
  makeKey,
  presignGetObject,
  presignPutObject,
  toS3Uri,
  moveObject,
} = require('../utils/s3Assets')

const signedUrlCache = require('../utils/signedUrlCache')

const router = express.Router()

// All Content Library routes require authentication.
router.use(authMiddleware)

function cleanString(v, { max = 5000 } = {}) {
  if (v === null || v === undefined) return ''
  const s = String(v).trim()
  if (!s) return ''
  return s.length > max ? s.slice(0, max) : s
}

function cleanNullableString(v, opts) {
  const s = cleanString(v, opts)
  return s ? s : null
}

function cleanStringArray(v, { maxItems = 100, maxLen = 200 } = {}) {
  const arr = Array.isArray(v) ? v : []
  const out = []
  for (const x of arr) {
    const s = cleanString(x, { max: maxLen })
    if (!s) continue
    if (!out.includes(s)) out.push(s)
    if (out.length >= maxItems) break
  }
  return out
}

function cleanBool(v, { defaultValue = false } = {}) {
  if (v === undefined || v === null) return defaultValue
  if (typeof v === 'boolean') return v
  const s = String(v).trim().toLowerCase()
  if (s === 'true' || s === '1' || s === 'yes') return true
  if (s === 'false' || s === '0' || s === 'no') return false
  return defaultValue
}

function ensureHttpsUrlOrEmpty(v) {
  const s = cleanString(v, { max: 2048 })
  if (!s) return ''
  try {
    const u = new URL(s)
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return ''
    return u.toString()
  } catch {
    return ''
  }
}

function ensureBulletText(value) {
  const s = cleanString(value, { max: 20000 })
  if (!s) return ''
  // Keep existing bullets; if it's a single line without leading bullet, prefix.
  if (s.startsWith('•')) return s
  if (s.startsWith('-')) return `• ${s.replace(/^-+\s*/, '')}`
  if (s.startsWith('*')) return `• ${s.replace(/^\*+\s*/, '')}`
  return `• ${s}`
}

function normalizeBioProfiles(v) {
  const arr = Array.isArray(v) ? v : []
  const out = []
  for (const p of arr) {
    if (!p || typeof p !== 'object') continue
    const id = cleanString(p.id, { max: 120 }) || `profile_${Date.now()}`
    const label = cleanString(p.label, { max: 120 }) || 'Tailored bio'
    const projectTypes = cleanStringArray(p.projectTypes, {
      maxItems: 30,
      maxLen: 60,
    })
    const bio = ensureBulletText(p.bio)
    const experience = ensureBulletText(p.experience)
    out.push({ id, label, projectTypes, bio, experience })
    if (out.length >= 20) break
  }
  return out
}

function assertVersion({ existing, expectedVersion }) {
  if (expectedVersion === undefined || expectedVersion === null) return null
  const exp = Number(expectedVersion)
  const cur =
    existing && existing.version !== undefined && existing.version !== null
      ? Number(existing.version)
      : 0
  if (!Number.isFinite(exp)) return 'Invalid version'
  if (exp !== cur) return `Version conflict (expected ${exp}, current ${cur})`
  return null
}

async function withSignedHeadshotUrl(member) {
  if (!member || typeof member !== 'object') return member
  const key = String(member.headshotS3Key || '').trim()
  if (!key) return member

  try {
    const cached = signedUrlCache.get(`headshot:${key}`)
    if (cached?.url) {
      return {
        ...member,
        headshotUrl: cached.url,
        headshotS3Uri:
          member.headshotS3Uri ||
          toS3Uri({ bucket: getAssetsBucketName(), key }),
      }
    }

    const expiresInSeconds = 3600
    const { url } = await presignGetObject({ key, expiresInSeconds })
    signedUrlCache.set(`headshot:${key}`, {
      url,
      expiresAtMs: Date.now() + (expiresInSeconds - 90) * 1000,
    })
    return {
      ...member,
      headshotUrl: url,
      headshotS3Uri:
        member.headshotS3Uri || toS3Uri({ bucket: getAssetsBucketName(), key }),
    }
  } catch (_e) {
    // If signing fails (missing bucket env, bad key, etc.), fall back to stored headshotUrl.
    return member
  }
}

async function normalizeMemberHeadshotStorage(member) {
  if (!member || typeof member !== 'object') return member
  const memberId = String(member.memberId || '').trim()
  const key = String(member.headshotS3Key || '').trim()
  if (!memberId || !key) return member

  // Only auto-relocate keys that were uploaded before the memberId existed.
  // Example: team/unassigned/headshot/<uuid>.png -> team/member_123/headshot/<uuid>.png
  if (!key.startsWith('team/unassigned/')) return member

  const newKey = makeKey({
    kind: 'headshot',
    fileName: key, // used only to preserve extension
    memberId,
  })

  try {
    await moveObject({ sourceKey: key, destKey: newKey })
    return {
      ...member,
      headshotS3Key: newKey,
      headshotS3Uri: toS3Uri({ bucket: getAssetsBucketName(), key: newKey }),
    }
  } catch (e) {
    // Non-blocking: if S3 move fails, keep the original key.
    console.error('Failed to relocate headshot object:', e)
    return member
  }
}

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
    const companyId = cleanNullableString(req.body?.companyId, { max: 80 })
    const name = cleanString(req.body?.name, { max: 200 })
    const description = cleanString(req.body?.description, { max: 20000 })
    if (!name || !description) {
      return res
        .status(400)
        .json({ error: 'name and description are required' })
    }

    const created = await upsertCompany({
      companyId,
      name,
      tagline: cleanString(req.body?.tagline, { max: 500 }),
      description,
      founded: cleanNullableString(req.body?.founded, { max: 120 }),
      location: cleanString(req.body?.location, { max: 500 }),
      website: ensureHttpsUrlOrEmpty(req.body?.website),
      email: cleanString(req.body?.email, { max: 200 }),
      phone: cleanString(req.body?.phone, { max: 60 }),
      coreCapabilities: cleanStringArray(req.body?.coreCapabilities, {
        maxItems: 50,
        maxLen: 200,
      }),
      certifications: cleanStringArray(req.body?.certifications, {
        maxItems: 50,
        maxLen: 200,
      }),
      industryFocus: cleanStringArray(req.body?.industryFocus, {
        maxItems: 50,
        maxLen: 200,
      }),
      missionStatement: cleanString(req.body?.missionStatement, { max: 20000 }),
      visionStatement: cleanString(req.body?.visionStatement, { max: 20000 }),
      values: cleanStringArray(req.body?.values, { maxItems: 50, maxLen: 200 }),
      statistics:
        req.body?.statistics && typeof req.body.statistics === 'object'
          ? req.body.statistics
          : null,
      socialMedia:
        req.body?.socialMedia && typeof req.body.socialMedia === 'object'
          ? req.body.socialMedia
          : null,
      coverLetter: cleanString(req.body?.coverLetter, { max: 50000 }),
      firmQualificationsAndExperience: cleanString(
        req.body?.firmQualificationsAndExperience,
        { max: 50000 },
      ),
      lastUpdated: new Date().toISOString(),
      sharedInfo:
        req.body?.sharedInfo && typeof req.body.sharedInfo === 'object'
          ? req.body.sharedInfo
          : null,
      isActive: true,
      version: 1,
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

    const conflict = assertVersion({
      existing,
      expectedVersion: (req.body || {}).version,
    })
    if (conflict) return res.status(409).json({ error: conflict })

    const updates = {
      ...req.body,
      companyId: req.params.companyId,
      lastUpdated: new Date().toISOString(),
    }

    // Normalize common fields so we don't persist junk.
    if ('name' in updates)
      updates.name = cleanString(updates.name, { max: 200 })
    if ('tagline' in updates)
      updates.tagline = cleanString(updates.tagline, { max: 500 })
    if ('description' in updates)
      updates.description = cleanString(updates.description, { max: 20000 })
    if ('website' in updates)
      updates.website = ensureHttpsUrlOrEmpty(updates.website)
    if ('email' in updates)
      updates.email = cleanString(updates.email, { max: 200 })
    if ('phone' in updates)
      updates.phone = cleanString(updates.phone, { max: 60 })
    if ('coreCapabilities' in updates)
      updates.coreCapabilities = cleanStringArray(updates.coreCapabilities)
    if ('certifications' in updates)
      updates.certifications = cleanStringArray(updates.certifications)
    if ('industryFocus' in updates)
      updates.industryFocus = cleanStringArray(updates.industryFocus)
    if ('values' in updates) updates.values = cleanStringArray(updates.values)

    const nextVersion =
      existing.version !== undefined && existing.version !== null
        ? Number(existing.version) + 1
        : 1
    updates.version = nextVersion

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

    const conflict = assertVersion({
      existing,
      expectedVersion: (req.body || {}).version,
    })
    if (conflict) return res.status(409).json({ error: conflict })

    const nextVersion =
      existing.version !== undefined && existing.version !== null
        ? Number(existing.version) + 1
        : 1

    const updated = await upsertCompany({
      ...existing,
      ...req.body,
      companyId,
      lastUpdated: new Date().toISOString(),
      version: nextVersion,
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
    const active = members.filter(
      (m) => m && (m.isActive === undefined || m.isActive === true),
    )
    const signed = await Promise.all(active.map(withSignedHeadshotUrl))
    res.json(signed)
  } catch (error) {
    console.error('Error fetching team members:', error)
    res.status(500).json({ error: 'Failed to fetch team members' })
  }
})

// Create a presigned PUT URL for uploading a headshot to the backend S3 bucket.
// The client uploads directly to S3, then persists the returned `headshotS3Key`
// on the TeamMember record via create/update.
router.post('/team/headshot/presign', async (req, res) => {
  try {
    const { fileName, contentType, memberId } = req.body || {}
    if (!fileName)
      return res.status(400).json({ error: 'fileName is required' })
    if (!contentType)
      return res.status(400).json({ error: 'contentType is required' })

    const ct = String(contentType).trim().toLowerCase()
    if (!ct.startsWith('image/')) {
      return res.status(400).json({ error: 'Only image uploads are allowed' })
    }
    const allowedExt = new Set(['.jpg', '.jpeg', '.png', '.webp'])
    const file = String(fileName).trim()
    const extMatch = file.toLowerCase().match(/(\.[a-z0-9]{1,10})$/)
    const ext = extMatch ? extMatch[1] : ''
    if (ext && !allowedExt.has(ext)) {
      return res.status(400).json({
        error: `Unsupported file type. Allowed: ${Array.from(allowedExt).join(
          ', ',
        )}`,
      })
    }

    const key = makeKey({
      kind: 'headshot',
      fileName: String(fileName),
      memberId: memberId ? String(memberId) : undefined,
    })

    const put = await presignPutObject({
      key,
      contentType: String(contentType),
      expiresInSeconds: 900,
    })
    const get = await presignGetObject({ key, expiresInSeconds: 3600 })

    return res.json({
      ok: true,
      bucket: put.bucket,
      key,
      s3Uri: toS3Uri({ bucket: put.bucket, key }),
      putUrl: put.url,
      getUrl: get.url,
      expiresInSeconds: { put: 900, get: 3600 },
    })
  } catch (e) {
    console.error('Error presigning team headshot upload:', e)
    return res.status(500).json({
      error: 'Failed to create upload URL',
      message: e?.message,
    })
  }
})

router.post('/team', async (req, res) => {
  try {
    const version = 1
    const created = await upsertTeamMember({
      memberId: cleanNullableString(req.body?.memberId, { max: 80 }),
      nameWithCredentials: cleanString(req.body?.nameWithCredentials, {
        max: 200,
      }),
      name: cleanString(req.body?.name, { max: 200 }),
      position: cleanString(req.body?.position, { max: 200 }),
      title: cleanString(req.body?.title, { max: 200 }),
      email: cleanString(req.body?.email, { max: 200 }),
      companyId: cleanNullableString(req.body?.companyId, { max: 80 }),
      biography: ensureBulletText(req.body?.biography),
      experienceYears: req.body?.experienceYears ?? undefined,
      education: cleanStringArray(req.body?.education, {
        maxItems: 50,
        maxLen: 200,
      }),
      certifications: cleanStringArray(req.body?.certifications, {
        maxItems: 50,
        maxLen: 200,
      }),
      bioProfiles: normalizeBioProfiles(req.body?.bioProfiles),
      // Back-compat: allow URL-based headshot; S3 key takes precedence for rendering.
      headshotUrl: ensureHttpsUrlOrEmpty(req.body?.headshotUrl),
      headshotS3Key: cleanNullableString(req.body?.headshotS3Key, {
        max: 1024,
      }),
      headshotS3Uri: cleanNullableString(req.body?.headshotS3Uri, {
        max: 2048,
      }),
      isActive: true,
      version,
    })
    const normalized = await normalizeMemberHeadshotStorage(created)
    const finalMember =
      normalized.headshotS3Key !== created.headshotS3Key
        ? await upsertTeamMember({
            ...normalized,
            memberId: created.memberId,
            version,
          })
        : normalized
    res.status(201).json(await withSignedHeadshotUrl(finalMember))
  } catch (error) {
    console.error('Error creating team member:', error)
    res.status(500).json({ error: 'Failed to create team member' })
  }
})

router.get('/team/:memberId', async (req, res) => {
  try {
    const member = await getTeamMemberById(req.params.memberId)
    if (!member) return res.status(404).json({ error: 'Team member not found' })
    res.json(await withSignedHeadshotUrl(member))
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

    const conflict = assertVersion({
      existing,
      expectedVersion: (req.body || {}).version,
    })
    if (conflict) return res.status(409).json({ error: conflict })

    const nextVersion =
      existing.version !== undefined && existing.version !== null
        ? Number(existing.version) + 1
        : 1
    const updated = await upsertTeamMember({
      ...existing,
      ...req.body,
      nameWithCredentials:
        'nameWithCredentials' in (req.body || {})
          ? cleanString(req.body?.nameWithCredentials, { max: 200 })
          : existing.nameWithCredentials,
      name:
        'name' in (req.body || {})
          ? cleanString(req.body?.name, { max: 200 })
          : existing.name,
      position:
        'position' in (req.body || {})
          ? cleanString(req.body?.position, { max: 200 })
          : existing.position,
      title:
        'title' in (req.body || {})
          ? cleanString(req.body?.title, { max: 200 })
          : existing.title,
      email:
        'email' in (req.body || {})
          ? cleanString(req.body?.email, { max: 200 })
          : existing.email,
      companyId:
        'companyId' in (req.body || {})
          ? cleanNullableString(req.body?.companyId, { max: 80 })
          : existing.companyId,
      biography:
        'biography' in (req.body || {})
          ? ensureBulletText(req.body?.biography)
          : existing.biography,
      education:
        'education' in (req.body || {})
          ? cleanStringArray(req.body?.education, { maxItems: 50, maxLen: 200 })
          : existing.education,
      certifications:
        'certifications' in (req.body || {})
          ? cleanStringArray(req.body?.certifications, {
              maxItems: 50,
              maxLen: 200,
            })
          : existing.certifications,
      bioProfiles:
        'bioProfiles' in (req.body || {})
          ? normalizeBioProfiles(req.body?.bioProfiles)
          : existing.bioProfiles,
      headshotUrl:
        'headshotUrl' in (req.body || {})
          ? ensureHttpsUrlOrEmpty(req.body?.headshotUrl)
          : existing.headshotUrl,
      headshotS3Key:
        'headshotS3Key' in (req.body || {})
          ? cleanNullableString(req.body?.headshotS3Key, { max: 1024 })
          : existing.headshotS3Key,
      headshotS3Uri:
        'headshotS3Uri' in (req.body || {})
          ? cleanNullableString(req.body?.headshotS3Uri, { max: 2048 })
          : existing.headshotS3Uri,
      memberId: req.params.memberId,
      version: nextVersion,
    })
    const normalized = await normalizeMemberHeadshotStorage(updated)
    const finalMember =
      normalized.headshotS3Key !== updated.headshotS3Key
        ? await upsertTeamMember({
            ...normalized,
            memberId: req.params.memberId,
            version: nextVersion,
          })
        : normalized
    res.json(await withSignedHeadshotUrl(finalMember))
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

router.get('/projects/:id', async (req, res) => {
  try {
    const project = await getPastProjectById(req.params.id)
    if (!project) return res.status(404).json({ error: 'Project not found' })
    res.json(project)
  } catch (error) {
    console.error('Error fetching project:', error)
    res.status(500).json({ error: 'Failed to fetch project' })
  }
})

router.post('/projects', async (req, res) => {
  try {
    const title = cleanString(req.body?.title, { max: 200 })
    const clientName = cleanString(req.body?.clientName, { max: 200 })
    const description = cleanString(req.body?.description, { max: 20000 })
    const industry = cleanString(req.body?.industry, { max: 200 })
    const projectType = cleanString(req.body?.projectType, { max: 120 })
    const duration = cleanString(req.body?.duration, { max: 120 })
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
      title,
      clientName,
      description,
      industry,
      projectType,
      duration,
      keyOutcomes: cleanStringArray(req.body?.keyOutcomes, {
        maxItems: 50,
        maxLen: 300,
      }),
      technologies: cleanStringArray(req.body?.technologies, {
        maxItems: 50,
        maxLen: 120,
      }),
      challenges: cleanStringArray(req.body?.challenges, {
        maxItems: 50,
        maxLen: 300,
      }),
      solutions: cleanStringArray(req.body?.solutions, {
        maxItems: 50,
        maxLen: 300,
      }),
      isActive: true,
      isPublic: req.body?.isPublic !== false,
      version: 1,
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

    const conflict = assertVersion({
      existing,
      expectedVersion: (req.body || {}).version,
    })
    if (conflict) return res.status(409).json({ error: conflict })

    const nextVersion =
      existing.version !== undefined && existing.version !== null
        ? Number(existing.version) + 1
        : 1
    const updated = await upsertPastProject({
      ...existing,
      ...req.body,
      title:
        'title' in (req.body || {})
          ? cleanString(req.body?.title, { max: 200 })
          : existing.title,
      clientName:
        'clientName' in (req.body || {})
          ? cleanString(req.body?.clientName, { max: 200 })
          : existing.clientName,
      description:
        'description' in (req.body || {})
          ? cleanString(req.body?.description, { max: 20000 })
          : existing.description,
      industry:
        'industry' in (req.body || {})
          ? cleanString(req.body?.industry, { max: 200 })
          : existing.industry,
      projectType:
        'projectType' in (req.body || {})
          ? cleanString(req.body?.projectType, { max: 120 })
          : existing.projectType,
      duration:
        'duration' in (req.body || {})
          ? cleanString(req.body?.duration, { max: 120 })
          : existing.duration,
      keyOutcomes:
        'keyOutcomes' in (req.body || {})
          ? cleanStringArray(req.body?.keyOutcomes, {
              maxItems: 50,
              maxLen: 300,
            })
          : existing.keyOutcomes,
      technologies:
        'technologies' in (req.body || {})
          ? cleanStringArray(req.body?.technologies, {
              maxItems: 50,
              maxLen: 120,
            })
          : existing.technologies,
      challenges:
        'challenges' in (req.body || {})
          ? cleanStringArray(req.body?.challenges, {
              maxItems: 50,
              maxLen: 300,
            })
          : existing.challenges,
      solutions:
        'solutions' in (req.body || {})
          ? cleanStringArray(req.body?.solutions, { maxItems: 50, maxLen: 300 })
          : existing.solutions,
      projectId: req.params.id,
      version: nextVersion,
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

router.get('/references/:id', async (req, res) => {
  try {
    const ref = await getProjectReferenceById(req.params.id)
    if (!ref) return res.status(404).json({ error: 'Reference not found' })
    res.json(ref)
  } catch (error) {
    console.error('Error fetching reference:', error)
    res.status(500).json({ error: 'Failed to fetch reference' })
  }
})

router.post('/references', async (req, res) => {
  try {
    const organizationName = cleanString(req.body?.organizationName, {
      max: 200,
    })
    const contactName = cleanString(req.body?.contactName, { max: 200 })
    const contactEmail = cleanString(req.body?.contactEmail, { max: 200 })
    const scopeOfWork = cleanString(req.body?.scopeOfWork, { max: 20000 })
    if (!organizationName || !contactName || !contactEmail || !scopeOfWork) {
      return res.status(400).json({ error: 'Missing required fields' })
    }

    const created = await upsertProjectReference({
      ...req.body,
      organizationName,
      contactName,
      contactEmail,
      scopeOfWork,
      contactTitle: cleanString(req.body?.contactTitle, { max: 200 }),
      additionalTitle: cleanString(req.body?.additionalTitle, { max: 200 }),
      contactPhone: cleanString(req.body?.contactPhone, { max: 60 }),
      timePeriod: cleanString(req.body?.timePeriod, { max: 120 }),
      projectType: cleanString(req.body?.projectType, { max: 120 }),
      isPublic: Boolean(req.body?.isPublic !== false),
      isActive: true,
      version: 1,
    })

    res.status(201).json(created)
  } catch (error) {
    console.error('Error creating reference:', error)
    res.status(500).json({ error: 'Failed to create reference' })
  }
})

router.put('/references/:id', async (req, res) => {
  try {
    const existing = await getProjectReferenceById(req.params.id)
    if (!existing) return res.status(404).json({ error: 'Reference not found' })

    const conflict = assertVersion({
      existing,
      expectedVersion: (req.body || {}).version,
    })
    if (conflict) return res.status(409).json({ error: conflict })

    const nextVersion =
      existing.version !== undefined && existing.version !== null
        ? Number(existing.version) + 1
        : 1

    const updated = await upsertProjectReference({
      ...existing,
      ...req.body,
      organizationName:
        'organizationName' in (req.body || {})
          ? cleanString(req.body?.organizationName, { max: 200 })
          : existing.organizationName,
      contactName:
        'contactName' in (req.body || {})
          ? cleanString(req.body?.contactName, { max: 200 })
          : existing.contactName,
      contactEmail:
        'contactEmail' in (req.body || {})
          ? cleanString(req.body?.contactEmail, { max: 200 })
          : existing.contactEmail,
      scopeOfWork:
        'scopeOfWork' in (req.body || {})
          ? cleanString(req.body?.scopeOfWork, { max: 20000 })
          : existing.scopeOfWork,
      contactTitle:
        'contactTitle' in (req.body || {})
          ? cleanString(req.body?.contactTitle, { max: 200 })
          : existing.contactTitle,
      additionalTitle:
        'additionalTitle' in (req.body || {})
          ? cleanString(req.body?.additionalTitle, { max: 200 })
          : existing.additionalTitle,
      contactPhone:
        'contactPhone' in (req.body || {})
          ? cleanString(req.body?.contactPhone, { max: 60 })
          : existing.contactPhone,
      timePeriod:
        'timePeriod' in (req.body || {})
          ? cleanString(req.body?.timePeriod, { max: 120 })
          : existing.timePeriod,
      projectType:
        'projectType' in (req.body || {})
          ? cleanString(req.body?.projectType, { max: 120 })
          : existing.projectType,
      referenceId: req.params.id,
      isActive: req.body?.isActive !== false,
      version: nextVersion,
    })
    res.json(updated)
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
