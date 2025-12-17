const { put, get, update, del, query } = require('./ddb')
const { newId } = require('./ids')
const { nowIso, typePk } = require('./keys')

function templateKey(templateId) {
  return { pk: `TEMPLATE#${String(templateId)}`, sk: 'PROFILE' }
}

function normalizeTemplate(item) {
  if (!item) return null
  const out = { ...item, id: item.templateId }
  delete out.pk
  delete out.sk
  delete out.gsi1pk
  delete out.gsi1sk
  delete out.entityType
  delete out.templateId
  return out
}

async function getTemplateById(templateId) {
  const { Item } = await get({ Key: templateKey(templateId) })
  return Item ? normalizeTemplate(Item) : null
}

async function listTemplates({ limit = 200 } = {}) {
  const resp = await query({
    IndexName: 'GSI1',
    KeyConditionExpression: 'gsi1pk = :pk',
    ExpressionAttributeValues: { ':pk': typePk('TEMPLATE') },
    ScanIndexForward: false,
    Limit: Math.min(200, Math.max(1, Number(limit) || 200)),
  })
  return (resp.Items || []).map(normalizeTemplate)
}

async function createTemplate({
  name,
  description = '',
  projectType = '',
  sections = [],
  tags = [],
  isActive = true,
  version = 1,
  createdBy = 'user',
  lastModifiedBy = 'user',
}) {
  const templateId = newId('tpl')
  const now = nowIso()
  const item = {
    ...templateKey(templateId),
    entityType: 'Template',
    templateId,
    name,
    description,
    projectType,
    sections,
    tags,
    isActive: !!isActive,
    version,
    createdBy,
    lastModifiedBy,
    createdAt: now,
    updatedAt: now,
    gsi1pk: typePk('TEMPLATE'),
    gsi1sk: `${now}#${templateId}`,
  }
  await put({ Item: item, ConditionExpression: 'attribute_not_exists(pk)' })
  return normalizeTemplate(item)
}

async function updateTemplate(templateId, patch) {
  const allowed = [
    'name',
    'description',
    'projectType',
    'sections',
    'isActive',
    'tags',
    'version',
    'lastModifiedBy',
  ]
  const updates = {}
  Object.keys(patch || {}).forEach((k) => {
    if (allowed.includes(k)) updates[k] = patch[k]
  })

  const now = nowIso()
  const sets = []
  const values = { ':u': now, ':g': `${now}#${String(templateId)}` }
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

  const resp = await update({
    Key: templateKey(templateId),
    UpdateExpression: `SET ${sets.join(', ')}`,
    ExpressionAttributeNames: names,
    ExpressionAttributeValues: values,
    ReturnValues: 'ALL_NEW',
  })
  return normalizeTemplate(resp.Attributes)
}

async function deleteTemplate(templateId) {
  await del({ Key: templateKey(templateId) })
  return true
}

module.exports = {
  getTemplateById,
  listTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
}
