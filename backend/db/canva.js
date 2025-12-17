const { put, get, del, query } = require('./ddb')
const { nowIso, typePk } = require('./keys')

// --- Connection ---
function connectionKey(userId) {
  return { pk: `USER#${String(userId)}`, sk: 'CANVA#CONNECTION' }
}

function normalize(item) {
  if (!item) return null
  const out = { ...item }
  delete out.pk
  delete out.sk
  delete out.gsi1pk
  delete out.gsi1sk
  delete out.entityType
  return out
}

async function upsertConnectionForUser(userId, fields) {
  const now = nowIso()
  const item = {
    ...connectionKey(userId),
    entityType: 'CanvaConnection',
    userId: String(userId),
    accessTokenEnc: fields.accessTokenEnc || null,
    refreshTokenEnc: fields.refreshTokenEnc || null,
    tokenType: fields.tokenType || 'bearer',
    scopes: Array.isArray(fields.scopes) ? fields.scopes : [],
    expiresAt: fields.expiresAt || null, // store ISO string or null
    updatedAt: now,
    gsi1pk: typePk('CANVA_CONNECTION'),
    gsi1sk: `${now}#${String(userId)}`,
  }
  await put({ Item: item })
  return normalize(item)
}

async function getConnectionForUser(userId) {
  const { Item } = await get({ Key: connectionKey(userId) })
  return normalize(Item)
}

async function deleteConnectionForUser(userId) {
  await del({ Key: connectionKey(userId) })
  return true
}

// --- Company mapping ---
function companyMappingKey(companyId) {
  return { pk: `COMPANY#${String(companyId)}`, sk: 'CANVA#MAPPING' }
}

async function upsertCompanyMapping(
  companyId,
  { brandTemplateId, fieldMapping },
) {
  const now = nowIso()
  const item = {
    ...companyMappingKey(companyId),
    entityType: 'CanvaCompanyTemplate',
    companyId: String(companyId),
    brandTemplateId: String(brandTemplateId),
    fieldMapping:
      fieldMapping && typeof fieldMapping === 'object' ? fieldMapping : {},
    updatedAt: now,
    gsi1pk: typePk('CANVA_COMPANY_TEMPLATE'),
    gsi1sk: `${now}#${String(companyId)}`,
  }
  await put({ Item: item })
  return normalize(item)
}

async function getCompanyMapping(companyId) {
  const { Item } = await get({ Key: companyMappingKey(companyId) })
  return normalize(Item)
}

async function listCompanyMappings({ limit = 200 } = {}) {
  const resp = await query({
    IndexName: 'GSI1',
    KeyConditionExpression: 'gsi1pk = :pk',
    ExpressionAttributeValues: { ':pk': typePk('CANVA_COMPANY_TEMPLATE') },
    ScanIndexForward: false,
    Limit: Math.min(200, Math.max(1, Number(limit) || 200)),
  })
  return (resp.Items || []).map(normalize)
}

// --- Asset links ---
function assetLinkKey({ ownerType, ownerId, kind }) {
  return {
    pk: `CANVA_ASSET#${String(ownerType)}#${String(ownerId)}`,
    sk: `KIND#${String(kind)}`,
  }
}

async function upsertAssetLink({
  ownerType,
  ownerId,
  kind,
  canvaAssetId,
  meta,
  sourceUrl,
}) {
  const now = nowIso()
  const item = {
    ...assetLinkKey({ ownerType, ownerId, kind }),
    entityType: 'CanvaAssetLink',
    ownerType: String(ownerType),
    ownerId: String(ownerId),
    kind: String(kind),
    canvaAssetId: String(canvaAssetId),
    sourceUrl: sourceUrl ? String(sourceUrl) : null,
    meta: meta && typeof meta === 'object' ? meta : {},
    updatedAt: now,
    gsi1pk: typePk('CANVA_ASSET_LINK'),
    gsi1sk: `${now}#${String(ownerType)}#${String(ownerId)}#${String(kind)}`,
  }
  await put({ Item: item })
  return normalize(item)
}

async function getAssetLink({ ownerType, ownerId, kind }) {
  const { Item } = await get({
    Key: assetLinkKey({ ownerType, ownerId, kind }),
  })
  return normalize(Item)
}

async function listAssetLinksForOwner({ ownerType, ownerId }) {
  const resp = await query({
    KeyConditionExpression: 'pk = :pk AND begins_with(sk, :sk)',
    ExpressionAttributeValues: {
      ':pk': `CANVA_ASSET#${String(ownerType)}#${String(ownerId)}`,
      ':sk': 'KIND#',
    },
    ScanIndexForward: false,
  })
  return (resp.Items || []).map(normalize)
}

// --- Proposal design cache ---
function proposalDesignKey({ proposalId, companyId, brandTemplateId }) {
  return {
    pk: `PROPOSAL#${String(proposalId)}`,
    sk: `CANVA#DESIGN#${String(companyId)}#${String(brandTemplateId)}`,
  }
}

async function upsertProposalDesignCache({
  proposalId,
  companyId,
  brandTemplateId,
  designId,
  designUrl,
  meta,
}) {
  const now = nowIso()
  const item = {
    ...proposalDesignKey({ proposalId, companyId, brandTemplateId }),
    entityType: 'CanvaProposalDesign',
    proposalId: String(proposalId),
    companyId: String(companyId),
    brandTemplateId: String(brandTemplateId),
    designId: String(designId),
    designUrl: designUrl ? String(designUrl) : null,
    meta: meta && typeof meta === 'object' ? meta : {},
    updatedAt: now,
    gsi1pk: typePk('CANVA_PROPOSAL_DESIGN'),
    gsi1sk: `${now}#${String(proposalId)}#${String(companyId)}#${String(
      brandTemplateId,
    )}`,
  }
  await put({ Item: item })
  return normalize(item)
}

async function getProposalDesignCache({
  proposalId,
  companyId,
  brandTemplateId,
}) {
  const { Item } = await get({
    Key: proposalDesignKey({ proposalId, companyId, brandTemplateId }),
  })
  return normalize(Item)
}

async function deleteProposalDesignCache({
  proposalId,
  companyId,
  brandTemplateId,
}) {
  await del({
    Key: proposalDesignKey({ proposalId, companyId, brandTemplateId }),
  })
  return true
}

module.exports = {
  // connection
  upsertConnectionForUser,
  getConnectionForUser,
  deleteConnectionForUser,
  // mappings
  upsertCompanyMapping,
  getCompanyMapping,
  listCompanyMappings,
  // assets
  upsertAssetLink,
  getAssetLink,
  listAssetLinksForOwner,
  // designs
  upsertProposalDesignCache,
  getProposalDesignCache,
  deleteProposalDesignCache,
}
