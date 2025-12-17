const { put, get, update, del, query } = require('./ddb')
const { newId } = require('./ids')
const { nowIso, typePk } = require('./keys')

function proposalKey(proposalId) {
  return { pk: `PROPOSAL#${String(proposalId)}`, sk: 'PROFILE' }
}

function proposalTypeItem(proposalId, updatedAt) {
  return {
    gsi1pk: typePk('PROPOSAL'),
    gsi1sk: `${updatedAt}#${String(proposalId)}`,
  }
}

function proposalRfpLinkKey(rfpId, proposalId) {
  return { pk: `RFP#${String(rfpId)}`, sk: `PROPOSAL#${String(proposalId)}` }
}

function normalizeProposalForApi(item, { includeSections = true } = {}) {
  if (!item) return null
  const out = { ...item, _id: item.proposalId, rfpId: item.rfpId }
  delete out.pk
  delete out.sk
  delete out.gsi1pk
  delete out.gsi1sk
  delete out.entityType
  delete out.proposalId
  if (!includeSections) delete out.sections
  return out
}

async function createProposal({
  rfpId,
  companyId = null,
  templateId,
  title,
  sections,
  customContent = {},
  status = 'draft',
  rfpSummary = null,
}) {
  const proposalId = newId('proposal')
  const createdAt = nowIso()
  const updatedAt = createdAt
  const item = {
    ...proposalKey(proposalId),
    entityType: 'Proposal',
    proposalId,
    rfpId: String(rfpId),
    companyId: companyId ? String(companyId) : null,
    templateId: String(templateId),
    title: String(title),
    status,
    sections: sections || {},
    customContent: customContent || {},
    review: {
      score: null,
      decision: '',
      notes: '',
      rubric: {},
      updatedAt: null,
    },
    createdAt,
    updatedAt,
    rfpSummary:
      rfpSummary && typeof rfpSummary === 'object' ? rfpSummary : null,
    ...proposalTypeItem(proposalId, updatedAt),
  }

  await put({ Item: item, ConditionExpression: 'attribute_not_exists(pk)' })

  // Upsert summary link under the RFP partition for fast compare-table queries.
  const link = {
    ...proposalRfpLinkKey(rfpId, proposalId),
    entityType: 'RfpProposalLink',
    proposalId,
    rfpId: String(rfpId),
    title: item.title,
    status: item.status,
    companyId: item.companyId,
    templateId: item.templateId,
    review: item.review,
    createdAt,
    updatedAt,
  }
  await put({ Item: link })

  return normalizeProposalForApi(item, { includeSections: true })
}

async function getProposalById(proposalId, { includeSections = true } = {}) {
  const { Item } = await get({ Key: proposalKey(proposalId) })
  return normalizeProposalForApi(Item, { includeSections })
}

async function listProposals({ page = 1, limit = 20 } = {}) {
  const p = Math.max(1, Number(page) || 1)
  const lim = Math.max(1, Math.min(200, Number(limit) || 20))
  const desired = p * lim

  let items = []
  let lastKey = null
  while (items.length < desired) {
    const resp = await query({
      IndexName: 'GSI1',
      KeyConditionExpression: 'gsi1pk = :pk',
      ExpressionAttributeValues: { ':pk': typePk('PROPOSAL') },
      ScanIndexForward: false,
      Limit: Math.min(200, desired - items.length),
      ExclusiveStartKey: lastKey || undefined,
    })
    const batch = Array.isArray(resp.Items) ? resp.Items : []
    items = items.concat(batch)
    lastKey = resp.LastEvaluatedKey || null
    if (!lastKey || batch.length === 0) break
  }

  const total = items.length
  const slice = items
    .slice((p - 1) * lim, p * lim)
    .map((it) => normalizeProposalForApi(it, { includeSections: false }))

  return {
    data: slice,
    pagination: {
      page: p,
      limit: lim,
      total,
      pages: Math.max(1, Math.ceil(total / lim)),
    },
  }
}

async function updateProposal(proposalId, updatesObj) {
  const allowed = [
    'title',
    'status',
    'sections',
    'customContent',
    'budgetBreakdown',
    'timelineDetails',
    'teamAssignments',
    'companyId',
    'templateId',
  ]
  const updates = {}
  Object.keys(updatesObj || {}).forEach((k) => {
    if (allowed.includes(k)) updates[k] = updatesObj[k]
  })

  const sets = []
  const values = { ':u': nowIso() }
  const names = {}
  let i = 0
  for (const [k, v] of Object.entries(updates)) {
    i += 1
    const nk = `#k${i}`
    const vk = `:v${i}`
    names[nk] = k
    values[vk] = v
    sets.push(`${nk} = ${vk}`)
  }
  sets.push('updatedAt = :u', 'gsi1sk = :g')
  values[':g'] = `${values[':u']}#${String(proposalId)}`

  const resp = await update({
    Key: proposalKey(proposalId),
    UpdateExpression: `SET ${sets.join(', ')}`,
    ExpressionAttributeNames: names,
    ExpressionAttributeValues: values,
    ReturnValues: 'ALL_NEW',
  })
  const updated = resp.Attributes
  if (updated?.rfpId) {
    // Update link item (best-effort)
    try {
      await put({
        Item: {
          ...proposalRfpLinkKey(updated.rfpId, proposalId),
          entityType: 'RfpProposalLink',
          proposalId,
          rfpId: String(updated.rfpId),
          title: updated.title,
          status: updated.status,
          companyId: updated.companyId || null,
          templateId: updated.templateId,
          review: updated.review,
          createdAt: updated.createdAt,
          updatedAt: updated.updatedAt,
        },
      })
    } catch {}
  }

  return normalizeProposalForApi(updated, { includeSections: true })
}

async function updateProposalReview(proposalId, reviewPatch) {
  const now = nowIso()
  const resp = await update({
    Key: proposalKey(proposalId),
    UpdateExpression: 'SET review = :r, updatedAt = :u, gsi1sk = :g',
    ExpressionAttributeValues: {
      ':r': reviewPatch,
      ':u': now,
      ':g': `${now}#${String(proposalId)}`,
    },
    ReturnValues: 'ALL_NEW',
  })
  const updated = resp.Attributes
  if (updated?.rfpId) {
    try {
      await put({
        Item: {
          ...proposalRfpLinkKey(updated.rfpId, proposalId),
          entityType: 'RfpProposalLink',
          proposalId,
          rfpId: String(updated.rfpId),
          title: updated.title,
          status: updated.status,
          companyId: updated.companyId || null,
          templateId: updated.templateId,
          review: updated.review,
          createdAt: updated.createdAt,
          updatedAt: updated.updatedAt,
        },
      })
    } catch {}
  }
  return normalizeProposalForApi(updated, { includeSections: true })
}

async function deleteProposal(proposalId) {
  const existing = await getProposalById(proposalId, { includeSections: false })
  await del({ Key: proposalKey(proposalId) })
  if (existing?.rfpId) {
    try {
      await del({ Key: proposalRfpLinkKey(existing.rfpId, proposalId) })
    } catch {}
  }
  return true
}

async function listProposalsByRfp(rfpId) {
  const resp = await query({
    KeyConditionExpression: 'pk = :pk AND begins_with(sk, :sk)',
    ExpressionAttributeValues: {
      ':pk': `RFP#${String(rfpId)}`,
      ':sk': 'PROPOSAL#',
    },
    ScanIndexForward: false,
  })
  const items = Array.isArray(resp.Items) ? resp.Items : []
  return items.map((it) => {
    const out = { ...it, _id: it.proposalId }
    delete out.pk
    delete out.sk
    delete out.entityType
    return out
  })
}

module.exports = {
  createProposal,
  getProposalById,
  listProposals,
  updateProposal,
  updateProposalReview,
  deleteProposal,
  listProposalsByRfp,
}
