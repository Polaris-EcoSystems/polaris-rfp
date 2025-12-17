const { put, get, update, del, query } = require('./ddb')
const { newId } = require('./ids')
const { nowIso, typePk } = require('./keys')
const {
  computeDateSanity,
  computeFitScore,
  checkDisqualification,
} = require('../services/rfpLogic')

function rfpKey(rfpId) {
  return { pk: `RFP#${String(rfpId)}`, sk: 'PROFILE' }
}

function rfpTypeItem(rfpId, createdAt) {
  return { gsi1pk: typePk('RFP'), gsi1sk: `${createdAt}#${String(rfpId)}` }
}

function normalizeRfpForApi(item) {
  if (!item) return null
  const obj = {
    ...item,
    _id: item.rfpId,
  }
  delete obj.pk
  delete obj.sk
  delete obj.gsi1pk
  delete obj.gsi1sk
  delete obj.entityType
  delete obj.rfpId

  // computed fields
  const disq = checkDisqualification(obj)
  obj.isDisqualified = !!disq
  const { warnings, meta } = computeDateSanity(obj)
  obj.dateWarnings = warnings
  obj.dateMeta = meta
  const fit = computeFitScore(obj)
  obj.fitScore = fit.score
  obj.fitReasons = fit.reasons

  return obj
}

async function createRfpFromAnalysis({
  analysis,
  sourceFileName,
  sourceFileSize,
}) {
  const rfpId = newId('rfp')
  const createdAt = nowIso()
  const item = {
    ...rfpKey(rfpId),
    entityType: 'RFP',
    rfpId,
    createdAt,
    updatedAt: createdAt,
    ...(analysis || {}),
    fileName: sourceFileName || '',
    fileSize: typeof sourceFileSize === 'number' ? sourceFileSize : 0,
    clientName: (analysis && analysis.clientName) || 'Unknown Client',
    ...rfpTypeItem(rfpId, createdAt),
  }

  await put({
    Item: item,
    ConditionExpression: 'attribute_not_exists(pk)',
  })

  return normalizeRfpForApi(item)
}

async function getRfpById(rfpId) {
  const { Item } = await get({ Key: rfpKey(rfpId) })
  return normalizeRfpForApi(Item)
}

async function listRfps({ page = 1, limit = 20 } = {}) {
  const p = Math.max(1, Number(page) || 1)
  const lim = Math.max(1, Math.min(200, Number(limit) || 20))
  const desired = p * lim

  let items = []
  let lastKey = null
  while (items.length < desired) {
    const resp = await query({
      IndexName: 'GSI1',
      KeyConditionExpression: 'gsi1pk = :pk',
      ExpressionAttributeValues: { ':pk': typePk('RFP') },
      ScanIndexForward: false,
      Limit: Math.min(200, desired - items.length),
      ExclusiveStartKey: lastKey || undefined,
    })
    const batch = Array.isArray(resp.Items) ? resp.Items : []
    items = items.concat(batch)
    lastKey = resp.LastEvaluatedKey || null
    if (!lastKey || batch.length === 0) break
  }

  const total = items.length // best-effort (avoid full scan); UI mainly needs list
  const slice = items.slice((p - 1) * lim, p * lim).map(normalizeRfpForApi)
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

async function updateRfp(rfpId, updatesObj) {
  const allowed = [
    'title',
    'clientName',
    'submissionDeadline',
    'questionsDeadline',
    'bidMeetingDate',
    'bidRegistrationDate',
    'budgetRange',
    'keyRequirements',
    'deliverables',
    'criticalInformation',
    'timeline',
    'projectDeadline',
    'projectType',
    'contactInformation',
    'location',
    'clarificationQuestions',
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
  sets.push('updatedAt = :u')

  const resp = await update({
    Key: rfpKey(rfpId),
    UpdateExpression: `SET ${sets.join(', ')}`,
    ExpressionAttributeNames: names,
    ExpressionAttributeValues: values,
    ReturnValues: 'ALL_NEW',
  })
  return normalizeRfpForApi(resp.Attributes)
}

async function deleteRfp(rfpId) {
  await del({ Key: rfpKey(rfpId) })
  return true
}

async function listRfpProposalSummaries(rfpId) {
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
    const out = { ...it }
    delete out.pk
    delete out.sk
    return out
  })
}

module.exports = {
  rfpKey,
  createRfpFromAnalysis,
  getRfpById,
  listRfps,
  updateRfp,
  deleteRfp,
  listRfpProposalSummaries,
}
