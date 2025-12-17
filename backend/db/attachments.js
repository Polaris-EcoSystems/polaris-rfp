const { put, get, del, query } = require('./ddb')
const { newId } = require('./ids')
const { nowIso } = require('./keys')

function attachmentKey(rfpId, attachmentId) {
  return {
    pk: `RFP#${String(rfpId)}`,
    sk: `ATTACHMENT#${String(attachmentId)}`,
  }
}

function normalizeAttachment(item) {
  if (!item) return null
  const out = { ...item, id: item.attachmentId }
  delete out.pk
  delete out.sk
  delete out.entityType
  delete out.attachmentId
  return out
}

async function addAttachments(rfpId, attachments) {
  const created = []
  for (const a of attachments || []) {
    const attachmentId = newId('att')
    const uploadedAt = nowIso()
    const item = {
      ...attachmentKey(rfpId, attachmentId),
      entityType: 'RfpAttachment',
      attachmentId,
      rfpId: String(rfpId),
      uploadedAt,
      ...a,
    }
    await put({ Item: item })
    created.push(normalizeAttachment(item))
  }
  return created
}

async function listAttachments(rfpId) {
  const resp = await query({
    KeyConditionExpression: 'pk = :pk AND begins_with(sk, :sk)',
    ExpressionAttributeValues: {
      ':pk': `RFP#${String(rfpId)}`,
      ':sk': 'ATTACHMENT#',
    },
    ScanIndexForward: false,
  })
  return (resp.Items || []).map(normalizeAttachment)
}

async function getAttachment(rfpId, attachmentId) {
  const { Item } = await get({ Key: attachmentKey(rfpId, attachmentId) })
  return Item ? normalizeAttachment(Item) : null
}

async function deleteAttachment(rfpId, attachmentId) {
  await del({ Key: attachmentKey(rfpId, attachmentId) })
  return true
}

module.exports = {
  addAttachments,
  listAttachments,
  getAttachment,
  deleteAttachment,
}
