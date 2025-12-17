const crypto = require('crypto')
const { getJwtSecret } = require('./jwtConfig')

function getKey() {
  const raw = process.env.CANVA_TOKEN_ENC_KEY || getJwtSecret()
  // 32-byte key for AES-256-GCM
  return crypto.createHash('sha256').update(String(raw)).digest()
}

function encryptString(plainText) {
  if (plainText === null || plainText === undefined) return null
  const text = String(plainText)
  const key = getKey()
  const iv = crypto.randomBytes(12)
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv)
  const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()])
  const tag = cipher.getAuthTag()
  // Format: v1:<iv>:<tag>:<ciphertext> (base64)
  return [
    'v1',
    iv.toString('base64'),
    tag.toString('base64'),
    encrypted.toString('base64'),
  ].join(':')
}

function decryptString(cipherText) {
  if (!cipherText) return null
  const raw = String(cipherText)
  const parts = raw.split(':')
  if (parts.length !== 4 || parts[0] !== 'v1') return null
  const [, ivB64, tagB64, dataB64] = parts
  const key = getKey()
  const iv = Buffer.from(ivB64, 'base64')
  const tag = Buffer.from(tagB64, 'base64')
  const data = Buffer.from(dataB64, 'base64')
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv)
  decipher.setAuthTag(tag)
  const decrypted = Buffer.concat([decipher.update(data), decipher.final()])
  return decrypted.toString('utf8')
}

module.exports = { encryptString, decryptString }
