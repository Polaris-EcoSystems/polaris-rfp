const { get, query, put, update, del } = require('./ddb')
const { newId } = require('./ids')
const { nowIso, typePk } = require('./keys')

function profileKey(prefix, id) {
  return { pk: `${prefix}#${String(id)}`, sk: 'PROFILE' }
}

function normalize(item, { idField } = {}) {
  if (!item) return null
  const out = { ...item }
  delete out.pk
  delete out.sk
  delete out.gsi1pk
  delete out.gsi1sk
  delete out.entityType
  if (idField && item[idField]) out._id = item[idField]
  return out
}

// --- Company ---
function companyKey(companyId) {
  return profileKey('COMPANY', companyId)
}

async function getCompanyByCompanyId(companyId) {
  const { Item } = await get({ Key: companyKey(companyId) })
  return normalize(Item, { idField: 'companyId' })
}

async function listCompanies({ limit = 200 } = {}) {
  const resp = await query({
    IndexName: 'GSI1',
    KeyConditionExpression: 'gsi1pk = :pk',
    ExpressionAttributeValues: { ':pk': typePk('COMPANY') },
    ScanIndexForward: false,
    Limit: Math.min(200, Math.max(1, Number(limit) || 200)),
  })
  return (resp.Items || []).map((it) => normalize(it, { idField: 'companyId' }))
}

async function upsertCompany(company) {
  const companyId = company.companyId || newId('company')
  const now = nowIso()
  const createdAt = company.createdAt || now
  const item = {
    ...companyKey(companyId),
    entityType: 'Company',
    companyId,
    createdAt,
    updatedAt: now,
    ...company,
    gsi1pk: typePk('COMPANY'),
    gsi1sk: `${now}#${companyId}`,
  }
  await put({ Item: item })
  return normalize(item, { idField: 'companyId' })
}

async function deleteCompany(companyId) {
  await del({ Key: companyKey(companyId) })
  return true
}

// --- Team members ---
function teamMemberKey(memberId) {
  return profileKey('TEAM', memberId)
}

async function getTeamMembersByIds(memberIds) {
  // No batchGet helper yet; query is fine for small selections by scanning type then filtering.
  const all = await listTeamMembers({ limit: 500 })
  const set = new Set((memberIds || []).map(String))
  return all.filter((m) => set.has(String(m.memberId)))
}

async function listTeamMembers({ limit = 200 } = {}) {
  const resp = await query({
    IndexName: 'GSI1',
    KeyConditionExpression: 'gsi1pk = :pk',
    ExpressionAttributeValues: { ':pk': typePk('TEAM_MEMBER') },
    ScanIndexForward: false,
    Limit: Math.min(500, Math.max(1, Number(limit) || 200)),
  })
  return (resp.Items || []).map((it) => normalize(it, { idField: 'memberId' }))
}

async function upsertTeamMember(member) {
  const memberId = member.memberId || newId('member')
  const now = nowIso()
  const createdAt = member.createdAt || now
  const item = {
    ...teamMemberKey(memberId),
    entityType: 'TeamMember',
    memberId,
    createdAt,
    updatedAt: now,
    ...member,
    gsi1pk: typePk('TEAM_MEMBER'),
    gsi1sk: `${now}#${memberId}`,
  }
  await put({ Item: item })
  return normalize(item, { idField: 'memberId' })
}

async function deleteTeamMember(memberId) {
  await del({ Key: teamMemberKey(memberId) })
  return true
}

async function getTeamMemberById(memberId) {
  const { Item } = await get({ Key: teamMemberKey(memberId) })
  return normalize(Item, { idField: 'memberId' })
}

// --- Project references ---
function projectRefKey(refId) {
  return profileKey('REF', refId)
}

async function listProjectReferences({ limit = 200 } = {}) {
  const resp = await query({
    IndexName: 'GSI1',
    KeyConditionExpression: 'gsi1pk = :pk',
    ExpressionAttributeValues: { ':pk': typePk('PROJECT_REFERENCE') },
    ScanIndexForward: false,
    Limit: Math.min(500, Math.max(1, Number(limit) || 200)),
  })
  return (resp.Items || []).map((it) =>
    normalize(it, { idField: 'referenceId' }),
  )
}

async function getProjectReferencesByIds(referenceIds) {
  const all = await listProjectReferences({ limit: 500 })
  const set = new Set((referenceIds || []).map(String))
  return all.filter((r) => set.has(String(r._id || r.referenceId)))
}

async function getProjectReferenceById(referenceId) {
  const { Item } = await get({ Key: projectRefKey(referenceId) })
  return normalize(Item, { idField: 'referenceId' })
}

async function upsertProjectReference(ref) {
  const referenceId = ref.referenceId || newId('ref')
  const now = nowIso()
  const createdAt = ref.createdAt || now
  const item = {
    ...projectRefKey(referenceId),
    entityType: 'ProjectReference',
    referenceId,
    createdAt,
    updatedAt: now,
    ...ref,
    gsi1pk: typePk('PROJECT_REFERENCE'),
    gsi1sk: `${now}#${referenceId}`,
  }
  await put({ Item: item })
  return normalize(item, { idField: 'referenceId' })
}

async function deleteProjectReference(referenceId) {
  await del({ Key: projectRefKey(referenceId) })
  return true
}

// --- Past projects ---
function pastProjectKey(projectId) {
  return profileKey('PROJECT', projectId)
}

async function listPastProjects({ limit = 200 } = {}) {
  const resp = await query({
    IndexName: 'GSI1',
    KeyConditionExpression: 'gsi1pk = :pk',
    ExpressionAttributeValues: { ':pk': typePk('PAST_PROJECT') },
    ScanIndexForward: false,
    Limit: Math.min(500, Math.max(1, Number(limit) || 200)),
  })
  return (resp.Items || []).map((it) => normalize(it, { idField: 'projectId' }))
}

async function getPastProjectById(projectId) {
  const { Item } = await get({ Key: pastProjectKey(projectId) })
  return normalize(Item, { idField: 'projectId' })
}

async function upsertPastProject(project) {
  const projectId = project.projectId || newId('proj')
  const now = nowIso()
  const createdAt = project.createdAt || now
  const item = {
    ...pastProjectKey(projectId),
    entityType: 'PastProject',
    projectId,
    createdAt,
    updatedAt: now,
    ...project,
    gsi1pk: typePk('PAST_PROJECT'),
    gsi1sk: `${now}#${projectId}`,
  }
  await put({ Item: item })
  return normalize(item, { idField: 'projectId' })
}

async function deletePastProject(projectId) {
  await del({ Key: pastProjectKey(projectId) })
  return true
}

module.exports = {
  // companies
  getCompanyByCompanyId,
  listCompanies,
  upsertCompany,
  deleteCompany,
  // team
  listTeamMembers,
  getTeamMembersByIds,
  getTeamMemberById,
  upsertTeamMember,
  deleteTeamMember,
  // references
  listProjectReferences,
  getProjectReferencesByIds,
  getProjectReferenceById,
  upsertProjectReference,
  deleteProjectReference,
  // past projects
  listPastProjects,
  getPastProjectById,
  upsertPastProject,
  deletePastProject,
}
