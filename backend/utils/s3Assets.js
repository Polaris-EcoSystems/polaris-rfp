const crypto = require('crypto')
const {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  CopyObjectCommand,
  DeleteObjectCommand,
} = require('@aws-sdk/client-s3')
const { getSignedUrl } = require('@aws-sdk/s3-request-presigner')

function getRegion() {
  return (
    process.env.AWS_REGION ||
    process.env.AWS_DEFAULT_REGION ||
    process.env.S3_REGION ||
    'us-east-1'
  )
}

function getAssetsBucketName() {
  const name = String(process.env.ASSETS_BUCKET_NAME || '').trim()
  if (!name) throw new Error('Missing ASSETS_BUCKET_NAME env var')
  return name
}

function makeKey({ kind, fileName, memberId } = {}) {
  const safeKind = String(kind || 'headshot').trim() || 'headshot'
  const safeMember = String(memberId || 'unassigned')
    .trim()
    .replace(/[^a-zA-Z0-9_-]/g, '_')
    .slice(0, 80)
  const ext = (() => {
    const raw = String(fileName || '').trim()
    const m = raw.match(/\.([a-zA-Z0-9]{1,10})$/)
    return m ? `.${m[1].toLowerCase()}` : ''
  })()
  const id = crypto.randomUUID()
  return `team/${safeMember}/${safeKind}/${id}${ext}`
}

function getClient() {
  return new S3Client({ region: getRegion() })
}

async function copyObject({ sourceKey, destKey } = {}) {
  const Bucket = getAssetsBucketName()
  const SourceKey = String(sourceKey || '').trim()
  const DestKey = String(destKey || '').trim()
  if (!SourceKey) throw new Error('Missing sourceKey for copyObject')
  if (!DestKey) throw new Error('Missing destKey for copyObject')

  // CopySource must be URL-encoded (especially for keys with spaces/special chars).
  const CopySource = `${Bucket}/${encodeURIComponent(SourceKey)}`
  await getClient().send(
    new CopyObjectCommand({
      Bucket,
      CopySource,
      Key: DestKey,
    }),
  )
  return { bucket: Bucket, sourceKey: SourceKey, destKey: DestKey }
}

async function deleteObject({ key } = {}) {
  const Bucket = getAssetsBucketName()
  const Key = String(key || '').trim()
  if (!Key) throw new Error('Missing key for deleteObject')
  await getClient().send(new DeleteObjectCommand({ Bucket, Key }))
  return { bucket: Bucket, key: Key }
}

async function moveObject({ sourceKey, destKey } = {}) {
  await copyObject({ sourceKey, destKey })
  await deleteObject({ key: sourceKey })
  return { bucket: getAssetsBucketName(), sourceKey, destKey }
}

async function presignPutObject({
  key,
  contentType,
  expiresInSeconds = 900,
} = {}) {
  const Bucket = getAssetsBucketName()
  const Key = String(key || '').trim()
  if (!Key) throw new Error('Missing key for presignPutObject')

  const cmd = new PutObjectCommand({
    Bucket,
    Key,
    ContentType: contentType ? String(contentType) : undefined,
    // Keep objects private; access via signed GET.
  })

  const url = await getSignedUrl(getClient(), cmd, {
    expiresIn: Math.max(60, Math.min(3600, Number(expiresInSeconds) || 900)),
  })

  return { bucket: Bucket, key: Key, url }
}

async function presignGetObject({ key, expiresInSeconds = 3600 } = {}) {
  const Bucket = getAssetsBucketName()
  const Key = String(key || '').trim()
  if (!Key) throw new Error('Missing key for presignGetObject')

  const cmd = new GetObjectCommand({ Bucket, Key })
  const url = await getSignedUrl(getClient(), cmd, {
    expiresIn: Math.max(
      60,
      Math.min(24 * 3600, Number(expiresInSeconds) || 3600),
    ),
  })
  return { bucket: Bucket, key: Key, url }
}

function toS3Uri({ bucket, key } = {}) {
  const b = String(bucket || '').trim()
  const k = String(key || '').trim()
  if (!b || !k) return ''
  return `s3://${b}/${k}`
}

module.exports = {
  getAssetsBucketName,
  makeKey,
  copyObject,
  deleteObject,
  moveObject,
  presignPutObject,
  presignGetObject,
  toS3Uri,
}
