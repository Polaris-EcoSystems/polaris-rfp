const express = require('express')
const crypto = require('crypto')
const jwt = require('jsonwebtoken')
const { authMiddleware } = require('../middleware/auth')
const { encryptString, decryptString } = require('../utils/tokenCrypto')
const { getProposalById, updateProposal } = require('../db/proposals')
const { getRfpById } = require('../db/rfps')
const {
  getCompanyByCompanyId,
  getTeamMembersByIds,
  getTeamMemberById,
  getProjectReferencesByIds,
} = require('../db/content')
const canvaDb = require('../db/canva')

const canvaClient = require('../services/canvaClient')
const {
  getCompanyTemplate,
  loadCompanyForProposal,
  buildDatasetValues,
  diagnoseDatasetValues,
} = require('../services/canvaProposalMapper')

const router = express.Router()

function getJwtSecret() {
  return process.env.JWT_SECRET || 'your-secret-key'
}

function getFrontendBaseUrl() {
  return (
    process.env.FRONTEND_BASE_URL ||
    process.env.NEXT_PUBLIC_FRONTEND_BASE_URL ||
    'https://rfp.polariseco.com'
  )
}

function safeJsonParse(s) {
  try {
    return JSON.parse(s)
  } catch {
    return null
  }
}

async function pollAssetJob(userId, mode, jobId) {
  if (mode === 'url') {
    return canvaClient.pollJob(
      () => canvaClient.getUrlAssetUploadJob(userId, jobId),
      { timeoutMs: 120000 },
    )
  }
  return canvaClient.pollJob(
    () => canvaClient.getAssetUploadJob(userId, jobId),
    {
      timeoutMs: 120000,
    },
  )
}

async function upsertAssetLink({ ownerType, ownerId, kind, asset, sourceUrl }) {
  const assetId = asset?.id ? String(asset.id) : ''
  if (!assetId) return null
  const doc = await canvaDb.upsertAssetLink({
    ownerType,
    ownerId,
    kind,
    canvaAssetId: assetId,
    sourceUrl: String(sourceUrl || ''),
    meta:
      asset && typeof asset === 'object'
        ? { ...asset, name: String(asset?.name || '') }
        : {},
  })
  return doc
}

// --- Auth / connect ---

router.get('/status', authMiddleware, async (req, res) => {
  try {
    const conn = await canvaDb.getConnectionForUser(req.user._id)
    if (!conn) return res.json({ connected: false, connection: null })
    const safe = { ...conn }
    delete safe.accessTokenEnc
    delete safe.refreshTokenEnc
    return res.json({ connected: true, connection: safe })
  } catch (e) {
    return res.status(500).json({ error: 'Failed to get Canva status' })
  }
})

router.post('/disconnect', authMiddleware, async (req, res) => {
  try {
    await canvaDb.deleteConnectionForUser(req.user._id)
    return res.json({ ok: true })
  } catch (e) {
    return res.status(500).json({ error: 'Failed to disconnect Canva' })
  }
})

router.get('/connect-url', authMiddleware, async (req, res) => {
  try {
    const pkceId = crypto.randomBytes(32).toString('base64url')
    const { codeVerifier, codeChallenge } = canvaClient.generatePkcePair()
    const expiresAt = new Date(Date.now() + 10 * 60 * 1000).toISOString()

    // Store return path inside state so we can redirect nicely after callback
    const returnTo = String(req.query.returnTo || '/integrations/canva')
    const state = jwt.sign(
      {
        userId: String(req.user._id),
        returnTo,
        pkceId,
        nonce: crypto.randomBytes(16).toString('base64url'),
      },
      getJwtSecret(),
      { expiresIn: '10m' },
    )

    const scopes = [
      'asset:read',
      'asset:write',
      'brandtemplate:meta:read',
      'brandtemplate:content:read',
      'design:content:read',
      'design:content:write',
      'design:meta:read',
    ]

    await canvaDb.upsertPkceForUser(req.user._id, pkceId, {
      codeVerifierEnc: encryptString(codeVerifier),
      expiresAt,
    })

    // Store PKCE verifier server-side; only send challenge to Canva.
    const url = canvaClient.buildAuthorizeUrl({
      state,
      scopes,
      codeChallenge,
    })
    return res.json({ url })
  } catch (e) {
    return res
      .status(500)
      .json({ error: e?.message || 'Failed to create connect URL' })
  }
})

// Canva redirects to this endpoint
router.get('/callback', async (req, res) => {
  try {
    const code = String(req.query.code || '')
    const state = String(req.query.state || '')
    const error = String(req.query.error || '')

    if (error) {
      return res.redirect(
        `${getFrontendBaseUrl()}/integrations/canva?error=${encodeURIComponent(
          error,
        )}`,
      )
    }

    if (!code || !state) {
      return res.redirect(
        `${getFrontendBaseUrl()}/integrations/canva?error=missing_code`,
      )
    }

    let decoded
    try {
      decoded = jwt.verify(state, getJwtSecret())
    } catch (e) {
      return res.redirect(
        `${getFrontendBaseUrl()}/integrations/canva?error=invalid_state`,
      )
    }

    const userId = decoded?.userId
    const returnTo = decoded?.returnTo || '/integrations/canva'
    const pkceId = decoded?.pkceId
    if (!userId) {
      return res.redirect(
        `${getFrontendBaseUrl()}/integrations/canva?error=missing_user`,
      )
    }

    const pkce = pkceId ? await canvaDb.getPkceForUser(userId, pkceId) : null
    if (!pkce || !pkce.codeVerifierEnc) {
      return res.redirect(
        `${getFrontendBaseUrl()}/integrations/canva?error=missing_pkce`,
      )
    }
    if (pkce.expiresAt && Date.now() > new Date(pkce.expiresAt).getTime()) {
      await canvaDb.deletePkceForUser(userId, pkceId)
      return res.redirect(
        `${getFrontendBaseUrl()}/integrations/canva?error=pkce_expired`,
      )
    }

    // One-time use
    await canvaDb.deletePkceForUser(userId, pkceId)

    const codeVerifier = decryptString(pkce.codeVerifierEnc)
    if (!codeVerifier) {
      return res.redirect(
        `${getFrontendBaseUrl()}/integrations/canva?error=invalid_pkce`,
      )
    }

    const token = await canvaClient.exchangeCodeForToken(code, codeVerifier)
    await canvaClient.upsertConnectionForUser(userId, token)

    return res.redirect(`${getFrontendBaseUrl()}${returnTo}?connected=1`)
  } catch (e) {
    console.error('Canva callback error:', e)
    return res.redirect(
      `${getFrontendBaseUrl()}/integrations/canva?error=callback_failed`,
    )
  }
})

// --- Brand templates + mapping (per company) ---

router.get('/brand-templates', authMiddleware, async (req, res) => {
  try {
    const query = String(req.query.query || '')
    const data = await canvaClient.listBrandTemplates(req.user._id, query)
    return res.json(data)
  } catch (e) {
    return res.status(500).json({
      error: 'Failed to list brand templates',
      message: e?.message,
    })
  }
})

router.get('/brand-templates/:id/dataset', authMiddleware, async (req, res) => {
  try {
    const id = String(req.params.id)
    const data = await canvaClient.getBrandTemplateDataset(req.user._id, id)
    return res.json(data)
  } catch (e) {
    return res.status(500).json({
      error: 'Failed to get template dataset',
      message: e?.message,
    })
  }
})

router.get('/company-mappings', authMiddleware, async (_req, res) => {
  try {
    const items = await canvaDb.listCompanyMappings({ limit: 200 })
    return res.json({ data: items })
  } catch (e) {
    return res.status(500).json({ error: 'Failed to load Canva mappings' })
  }
})

router.put('/company-mappings/:companyId', authMiddleware, async (req, res) => {
  try {
    const companyId = String(req.params.companyId || '').trim()
    const { brandTemplateId, fieldMapping } = req.body || {}
    if (!companyId)
      return res.status(400).json({ error: 'companyId is required' })
    if (!brandTemplateId) {
      return res.status(400).json({ error: 'brandTemplateId is required' })
    }

    const doc = await canvaDb.upsertCompanyMapping(companyId, {
      brandTemplateId: String(brandTemplateId).trim(),
      fieldMapping:
        fieldMapping && typeof fieldMapping === 'object' ? fieldMapping : {},
    })
    return res.json(doc)
  } catch (e) {
    return res.status(500).json({ error: 'Failed to save Canva mapping' })
  }
})

// --- Assets helpers (robust mapping for images) ---

router.post('/assets/upload-url', authMiddleware, async (req, res) => {
  try {
    const { name, url } = req.body || {}
    if (!name || !url) {
      return res.status(400).json({ error: 'name and url are required' })
    }
    const created = await canvaClient.createUrlAssetUploadJob(req.user._id, {
      name: String(name),
      url: String(url),
    })
    const jobId = created?.job?.id
    const finalJob = await pollAssetJob(req.user._id, 'url', jobId)
    if (finalJob?.job?.status !== 'success') {
      return res.status(400).json({
        error: 'Canva asset upload failed',
        details: finalJob?.job?.error || null,
      })
    }
    const asset = finalJob?.job?.asset || null
    return res.json({ ok: true, asset })
  } catch (e) {
    console.error('Canva upload-url error:', e)
    return res
      .status(500)
      .json({ error: 'Failed to upload asset from URL', message: e?.message })
  }
})

router.post('/assets/upload-base64', authMiddleware, async (req, res) => {
  try {
    const { name, dataBase64 } = req.body || {}
    if (!name || !dataBase64) {
      return res.status(400).json({ error: 'name and dataBase64 are required' })
    }
    const buf = Buffer.from(String(dataBase64), 'base64')
    if (!buf || buf.length === 0) {
      return res.status(400).json({ error: 'Invalid base64 data' })
    }
    const created = await canvaClient.createAssetUploadJob(req.user._id, {
      name: String(name),
      bytes: buf,
    })
    const jobId = created?.job?.id
    const finalJob = await pollAssetJob(req.user._id, 'raw', jobId)
    if (finalJob?.job?.status !== 'success') {
      return res.status(400).json({
        error: 'Canva asset upload failed',
        details: finalJob?.job?.error || null,
      })
    }
    const asset = finalJob?.job?.asset || null
    return res.json({ ok: true, asset })
  } catch (e) {
    console.error('Canva upload-base64 error:', e)
    return res
      .status(500)
      .json({ error: 'Failed to upload asset', message: e?.message })
  }
})

router.get('/companies/:companyId/logo', authMiddleware, async (req, res) => {
  try {
    const companyId = String(req.params.companyId || '').trim()
    if (!companyId)
      return res.status(400).json({ error: 'companyId is required' })
    const link = await canvaDb.getAssetLink({
      ownerType: 'company',
      ownerId: companyId,
      kind: 'logo',
    })
    return res.json({ ok: true, link: link || null })
  } catch (e) {
    return res
      .status(500)
      .json({ error: 'Failed to load company logo asset link' })
  }
})

router.post(
  '/companies/:companyId/logo/upload-url',
  authMiddleware,
  async (req, res) => {
    try {
      const companyId = String(req.params.companyId || '').trim()
      const { url, name } = req.body || {}
      if (!companyId)
        return res.status(400).json({ error: 'companyId is required' })
      if (!url) return res.status(400).json({ error: 'url is required' })
      const company = await getCompanyByCompanyId(companyId)
      if (!company) return res.status(404).json({ error: 'Company not found' })

      const created = await canvaClient.createUrlAssetUploadJob(req.user._id, {
        name: String(name || `${company.name} logo`),
        url: String(url),
      })
      const jobId = created?.job?.id
      const finalJob = await pollAssetJob(req.user._id, 'url', jobId)
      if (finalJob?.job?.status !== 'success') {
        return res.status(400).json({
          error: 'Canva asset upload failed',
          details: finalJob?.job?.error || null,
        })
      }
      const asset = finalJob?.job?.asset || null
      const link = await upsertAssetLink({
        ownerType: 'company',
        ownerId: companyId,
        kind: 'logo',
        asset,
        sourceUrl: String(url),
      })
      return res.json({
        ok: true,
        company,
        asset,
        link,
      })
    } catch (e) {
      console.error('Company logo upload error:', e)
      return res
        .status(500)
        .json({ error: 'Failed to upload company logo', message: e?.message })
    }
  },
)

router.get('/team/:memberId/headshot', authMiddleware, async (req, res) => {
  try {
    const memberId = String(req.params.memberId || '').trim()
    if (!memberId)
      return res.status(400).json({ error: 'memberId is required' })
    const link = await canvaDb.getAssetLink({
      ownerType: 'teamMember',
      ownerId: memberId,
      kind: 'headshot',
    })
    return res.json({ ok: true, link: link || null })
  } catch (e) {
    return res.status(500).json({ error: 'Failed to load headshot asset link' })
  }
})

router.post(
  '/team/:memberId/headshot/upload-url',
  authMiddleware,
  async (req, res) => {
    try {
      const memberId = String(req.params.memberId || '').trim()
      const { url, name } = req.body || {}
      if (!memberId)
        return res.status(400).json({ error: 'memberId is required' })
      if (!url) return res.status(400).json({ error: 'url is required' })
      const member = await getTeamMemberById(memberId)
      if (!member)
        return res.status(404).json({ error: 'Team member not found' })

      const created = await canvaClient.createUrlAssetUploadJob(req.user._id, {
        name: String(name || `${member.nameWithCredentials} headshot`),
        url: String(url),
      })
      const jobId = created?.job?.id
      const finalJob = await pollAssetJob(req.user._id, 'url', jobId)
      if (finalJob?.job?.status !== 'success') {
        return res.status(400).json({
          error: 'Canva asset upload failed',
          details: finalJob?.job?.error || null,
        })
      }
      const asset = finalJob?.job?.asset || null
      const link = await upsertAssetLink({
        ownerType: 'teamMember',
        ownerId: memberId,
        kind: 'headshot',
        asset,
        sourceUrl: String(url),
      })
      return res.json({
        ok: true,
        member,
        asset,
        link,
      })
    } catch (e) {
      console.error('Team headshot upload error:', e)
      return res
        .status(500)
        .json({ error: 'Failed to upload headshot', message: e?.message })
    }
  },
)

// --- Proposal -> Canva design + export ---

function collectSelectedIdsFromProposalSections(sections) {
  const teamIds = new Set()
  const referenceIds = new Set()
  const obj = sections && typeof sections === 'object' ? sections : {}
  Object.values(obj).forEach((s) => {
    const ids = Array.isArray(s?.selectedIds) ? s.selectedIds : []
    ids.forEach((id) => {
      const v = String(id || '').trim()
      if (!v) return
      if (v.startsWith('member_')) teamIds.add(v)
      else if (v.startsWith('company_')) return
      else if (v.startsWith('ref_') || /^[a-f0-9]{24}$/i.test(v))
        referenceIds.add(v)
    })
  })
  return {
    teamIds: Array.from(teamIds),
    referenceIds: Array.from(referenceIds),
  }
}

async function ensureCanvaDesignForProposal({
  userId,
  proposal,
  cfg,
  company,
  rfp,
}) {
  const companyId = proposal.companyId
  const proposalUpdatedAt = new Date(proposal.updatedAt || Date.now())

  const existing = await canvaDb.getProposalDesignCache({
    proposalId: proposal._id,
    companyId,
    brandTemplateId: cfg.brandTemplateId,
  })

  const isFresh =
    existing &&
    existing.meta?.lastProposalUpdatedAt &&
    new Date(existing.meta.lastProposalUpdatedAt).getTime() >=
      proposalUpdatedAt.getTime()

  if (isFresh) {
    return { cached: true, designId: existing.designId, record: existing }
  }

  const datasetResp = await canvaClient.getBrandTemplateDataset(
    userId,
    cfg.brandTemplateId,
  )
  const datasetDef = datasetResp?.dataset || {}

  const { teamIds, referenceIds } = collectSelectedIdsFromProposalSections(
    proposal.sections,
  )
  const [teamMembers, references, companyLogo, headshotLinks] =
    await Promise.all([
      teamIds.length ? getTeamMembersByIds(teamIds) : Promise.resolve([]),
      referenceIds.length
        ? getProjectReferencesByIds(referenceIds)
        : Promise.resolve([]),
      canvaDb.getAssetLink({
        ownerType: 'company',
        ownerId: companyId,
        kind: 'logo',
      }),
      teamIds.length
        ? Promise.all(
            teamIds.map((memberId) =>
              canvaDb.getAssetLink({
                ownerType: 'teamMember',
                ownerId: memberId,
                kind: 'headshot',
              }),
            ),
          ).then((xs) => xs.filter(Boolean))
        : Promise.resolve([]),
    ])
  const headshotByMemberId = {}
  headshotLinks.forEach((l) => {
    if (l?.ownerId && l?.canvaAssetId)
      headshotByMemberId[String(l.ownerId)] = l.canvaAssetId
  })

  const datasetValues = buildDatasetValues({
    datasetDef,
    mapping: cfg.fieldMapping || {},
    proposal,
    rfp,
    company,
    companyLogoAssetId: companyLogo?.canvaAssetId || '',
    teamMembers,
    headshotByMemberId,
    references,
  })

  const title =
    proposal.title || (rfp ? `Proposal for ${rfp.title}` : 'Proposal')
  const created = await canvaClient.createAutofillJob(userId, {
    brandTemplateId: cfg.brandTemplateId,
    title,
    data: datasetValues,
  })

  const jobId = created?.job?.id
  const finalJob = await canvaClient.pollJob(
    () => canvaClient.getAutofillJob(userId, jobId),
    { timeoutMs: 120000 },
  )
  if (finalJob?.job?.status !== 'success') {
    const err = new Error('Canva autofill failed')
    err.code = 'autofill_failed'
    err.details = finalJob?.job?.error || null
    throw err
  }

  const designSummary = finalJob?.job?.result?.design || null
  const designId = designSummary?.id
  if (!designId) {
    const err = new Error('No design ID returned from Canva')
    err.code = 'no_design_id'
    throw err
  }

  const now = new Date()
  const tempUrlsExpireAt = new Date(now.getTime() + 29 * 24 * 60 * 60 * 1000)
  const record = await canvaDb.upsertProposalDesignCache({
    proposalId: proposal._id,
    companyId,
    brandTemplateId: cfg.brandTemplateId,
    designId,
    designUrl: String(designSummary?.url || ''),
    meta: {
      editUrl: String(designSummary?.urls?.edit_url || ''),
      viewUrl: String(designSummary?.urls?.view_url || ''),
      tempUrlsExpireAt: tempUrlsExpireAt.toISOString(),
      lastProposalUpdatedAt: proposalUpdatedAt.toISOString(),
      lastGeneratedAt: now.toISOString(),
    },
  })

  return { cached: false, designId, record }
}

router.post(
  '/proposals/:id/create-design',
  authMiddleware,
  async (req, res) => {
    try {
      const id = String(req.params.id)
      const force = String(req.query.force || '') === '1'
      const proposal = await getProposalById(id, { includeSections: true })
      if (!proposal)
        return res.status(404).json({ error: 'Proposal not found' })

      const companyId = proposal.companyId
      if (!companyId) {
        return res.status(400).json({
          error: 'Proposal has no companyId; select a company/branding first.',
        })
      }

      const cfg = await getCompanyTemplate(companyId)
      if (!cfg) {
        return res.status(400).json({
          error: 'No Canva template configured for this company.',
        })
      }

      const rfp = await getRfpById(proposal.rfpId)
      const company = await loadCompanyForProposal(proposal)

      if (force) {
        await canvaDb.deleteProposalDesignCache({
          proposalId: proposal._id,
          companyId,
          brandTemplateId: cfg.brandTemplateId,
        })
      }

      const ensured = await ensureCanvaDesignForProposal({
        userId: req.user._id,
        proposal,
        cfg,
        company,
        rfp,
      })

      return res.json({
        ok: true,
        brandTemplateId: cfg.brandTemplateId,
        cached: ensured.cached,
        design: {
          id: ensured.record?.designId,
          url: ensured.record?.designUrl || '',
          urls: {
            edit_url: ensured.record?.meta?.editUrl || '',
            view_url: ensured.record?.meta?.viewUrl || '',
          },
        },
        meta: {
          lastGeneratedAt: ensured.record?.meta?.lastGeneratedAt || null,
          lastProposalUpdatedAt:
            ensured.record?.meta?.lastProposalUpdatedAt || null,
        },
      })
    } catch (e) {
      console.error('Create Canva design error:', e)
      return res.status(500).json({
        error: 'Failed to create Canva design',
        message: e?.message,
        details: e?.details || null,
      })
    }
  },
)

router.get('/proposals/:id/export-pdf', authMiddleware, async (req, res) => {
  try {
    const id = String(req.params.id)
    const proposal = await getProposalById(id, { includeSections: true })
    if (!proposal) return res.status(404).json({ error: 'Proposal not found' })
    const companyId = proposal.companyId
    if (!companyId) {
      return res.status(400).json({
        error: 'Proposal has no companyId; select a company/branding first.',
      })
    }
    const cfg = await getCompanyTemplate(companyId)
    if (!cfg) {
      return res.status(400).json({
        error: 'No Canva template configured for this company.',
      })
    }

    const rfp = await getRfpById(proposal.rfpId)
    const company = await loadCompanyForProposal(proposal)
    const ensured = await ensureCanvaDesignForProposal({
      userId: req.user._id,
      proposal,
      cfg,
      company,
      rfp,
    })
    const designId = ensured.designId

    const exportCreated = await canvaClient.createExportJob(req.user._id, {
      designId,
      format: 'pdf',
    })
    const exportId = exportCreated?.job?.id
    const exportFinal = await canvaClient.pollJob(
      () => canvaClient.getExportJob(req.user._id, exportId),
      { timeoutMs: 180000 },
    )
    if (exportFinal?.job?.status !== 'success') {
      return res.status(400).json({
        error: 'Canva export failed',
        details: exportFinal?.job?.error || null,
      })
    }

    const urls = Array.isArray(exportFinal?.job?.urls)
      ? exportFinal.job.urls
      : []
    if (urls.length === 0) {
      return res
        .status(400)
        .json({ error: 'No download URLs returned from Canva' })
    }

    // For PDF this should typically be one URL. If multiple, return JSON so UI can pick.
    if (urls.length > 1 && String(req.query.mode || '') === 'urls') {
      return res.json({ ok: true, designId, urls, cached: ensured.cached })
    }

    const dl = await canvaClient.downloadUrl(urls[0])
    res.setHeader('Content-Type', dl.contentType || 'application/pdf')
    res.setHeader(
      'Content-Disposition',
      `attachment; filename="${String(proposal.title || 'proposal').replace(
        /\\s+/g,
        '_',
      )}_canva.pdf"`,
    )
    return res.send(Buffer.from(dl.data))
  } catch (e) {
    console.error('Export Canva PDF error:', e)
    return res.status(500).json({
      error: 'Failed to export Canva PDF',
      message: e?.message,
    })
  }
})

// Validate how a proposal will fill the Canva dataset (no design creation)
router.post('/proposals/:id/validate', authMiddleware, async (req, res) => {
  try {
    const id = String(req.params.id)
    const proposal = await getProposalById(id, { includeSections: true })
    if (!proposal) return res.status(404).json({ error: 'Proposal not found' })
    const companyId = proposal.companyId
    if (!companyId) {
      return res.status(400).json({
        error: 'Proposal has no companyId; select a company/branding first.',
      })
    }
    const cfg = await getCompanyTemplate(companyId)
    if (!cfg) {
      return res.status(400).json({
        error: 'No Canva template configured for this company.',
      })
    }

    const rfp = await getRfpById(proposal.rfpId)
    const company = await loadCompanyForProposal(proposal)

    const datasetResp = await canvaClient.getBrandTemplateDataset(
      req.user._id,
      cfg.brandTemplateId,
    )
    const datasetDef = datasetResp?.dataset || {}

    const { teamIds, referenceIds } = collectSelectedIdsFromProposalSections(
      proposal.sections,
    )
    const [teamMembers, references, companyLogo, headshotLinks] =
      await Promise.all([
        teamIds.length ? getTeamMembersByIds(teamIds) : Promise.resolve([]),
        referenceIds.length
          ? getProjectReferencesByIds(referenceIds)
          : Promise.resolve([]),
        canvaDb.getAssetLink({
          ownerType: 'company',
          ownerId: companyId,
          kind: 'logo',
        }),
        teamIds.length
          ? Promise.all(
              teamIds.map((memberId) =>
                canvaDb.getAssetLink({
                  ownerType: 'teamMember',
                  ownerId: memberId,
                  kind: 'headshot',
                }),
              ),
            ).then((xs) => xs.filter(Boolean))
          : Promise.resolve([]),
      ])
    const headshotByMemberId = {}
    headshotLinks.forEach((l) => {
      if (l?.ownerId && l?.canvaAssetId)
        headshotByMemberId[String(l.ownerId)] = l.canvaAssetId
    })

    const diag = diagnoseDatasetValues({
      datasetDef,
      mapping: cfg.fieldMapping || {},
      proposal,
      rfp,
      company,
      companyLogoAssetId: companyLogo?.canvaAssetId || '',
      teamMembers,
      headshotByMemberId,
      references,
    })

    return res.json({
      ok: true,
      companyId,
      brandTemplateId: cfg.brandTemplateId,
      totals: diag.totals,
      results: diag.results,
    })
  } catch (e) {
    console.error('Canva validate error:', e)
    return res.status(500).json({
      error: 'Failed to validate Canva template',
      message: e?.message,
    })
  }
})

module.exports = router
