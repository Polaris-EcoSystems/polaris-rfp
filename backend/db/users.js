const bcrypt = require('bcryptjs')
const jwt = require('jsonwebtoken')
const crypto = require('crypto')
const { get, put, transactWrite, update, getTableName } = require('./ddb')
const { getJwtSecret, getJwtExpire } = require('../utils/jwtConfig')
const {
  nowIso,
  normalizeEmail,
  normalizeUsername,
  userProfileKey,
  usernameUniqueKey,
  emailUniqueKey,
  typePk,
} = require('./keys')

function newId() {
  // Node 22 supports crypto.randomUUID
  return require('crypto').randomUUID()
}

function jwtSecret() {
  return getJwtSecret()
}

function jwtExpire() {
  return getJwtExpire()
}

async function getUserById(userId) {
  const { Item } = await get({ Key: userProfileKey(userId) })
  return Item || null
}

async function getUserIdByUsernameOrEmail(login) {
  const raw = String(login || '').trim()
  if (!raw) return null

  const isEmail = raw.includes('@')
  const key = isEmail
    ? emailUniqueKey(normalizeEmail(raw))
    : usernameUniqueKey(normalizeUsername(raw))

  const { Item } = await get({ Key: key })
  return Item?.userId || null
}

async function createUser({ username, email, password }) {
  const usernameLower = normalizeUsername(username)
  const emailLower = normalizeEmail(email)

  const userId = newId()
  const createdAt = nowIso()

  const passwordHash = await bcrypt.hash(String(password), 12)

  const profile = {
    ...userProfileKey(userId),
    entityType: 'User',
    userId,
    username: usernameLower,
    email: emailLower,
    passwordHash,
    role: 'user',
    isActive: true,
    createdAt,
    updatedAt: createdAt,
    gsi1pk: typePk('USER'),
    gsi1sk: `${createdAt}#${userId}`,
  }

  const usernameUnique = {
    ...usernameUniqueKey(usernameLower),
    entityType: 'UserUsername',
    userId,
    username: usernameLower,
    createdAt,
    gsi1pk: typePk('USER_USERNAME'),
    gsi1sk: `${usernameLower}#${userId}`,
  }

  const emailUnique = {
    ...emailUniqueKey(emailLower),
    entityType: 'UserEmail',
    userId,
    email: emailLower,
    createdAt,
    gsi1pk: typePk('USER_EMAIL'),
    gsi1sk: `${emailLower}#${userId}`,
  }

  try {
    await transactWrite({
      TransactItems: [
        {
          Put: {
            TableName: getTableName(),
            Item: usernameUnique,
            ConditionExpression: 'attribute_not_exists(pk)',
          },
        },
        {
          Put: {
            TableName: getTableName(),
            Item: emailUnique,
            ConditionExpression: 'attribute_not_exists(pk)',
          },
        },
        {
          Put: {
            TableName: getTableName(),
            Item: profile,
            ConditionExpression: 'attribute_not_exists(pk)',
          },
        },
      ],
    })
  } catch (e) {
    // ConditionalCheckFailedException indicates duplicates
    if (e && String(e.name || '').includes('Conditional')) {
      const err = new Error('User already exists')
      err.code = 'user_exists'
      throw err
    }
    throw e
  }

  const token = jwt.sign({ userId, username: usernameLower }, jwtSecret(), {
    expiresIn: jwtExpire(),
  })

  return {
    user: { userId, username: usernameLower, email: emailLower, role: 'user' },
    token,
  }
}

async function verifyLogin({ usernameOrEmail, password }) {
  const userId = await getUserIdByUsernameOrEmail(usernameOrEmail)
  if (!userId) return null

  const user = await getUserById(userId)
  if (!user) return null

  if (!user.isActive) {
    const err = new Error('Account is inactive')
    err.code = 'inactive'
    throw err
  }

  const ok = await bcrypt.compare(
    String(password),
    String(user.passwordHash || ''),
  )
  if (!ok) return null

  // update lastLogin (best-effort)
  try {
    await update({
      Key: userProfileKey(userId),
      UpdateExpression: 'SET lastLogin = :t, updatedAt = :u',
      ExpressionAttributeValues: {
        ':t': nowIso(),
        ':u': nowIso(),
      },
    })
  } catch {}

  const token = jwt.sign({ userId, username: user.username }, jwtSecret(), {
    expiresIn: jwtExpire(),
  })

  return {
    token,
    user: { username: user.username, email: user.email, role: user.role },
  }
}

function sha256Hex(input) {
  return crypto.createHash('sha256').update(String(input)).digest('hex')
}

function resetTokenKey(tokenHash) {
  return { pk: `RESET#${String(tokenHash)}`, sk: 'TOKEN' }
}

async function requestPasswordReset({ email }) {
  const emailLower = normalizeEmail(email)
  if (!emailLower) return { ok: true }

  const userId = await getUserIdByUsernameOrEmail(emailLower)
  if (!userId) return { ok: true }

  const user = await getUserById(userId)
  if (!user || user.isActive === false) return { ok: true }

  const token = crypto.randomBytes(32).toString('base64url')
  const tokenHash = sha256Hex(token)
  const createdAt = nowIso()
  const expiresAt = new Date(Date.now() + 30 * 60 * 1000).toISOString() // 30m

  // Store token as a separate item so we can look it up by token hash.
  await put({
    Item: {
      ...resetTokenKey(tokenHash),
      entityType: 'PasswordResetToken',
      tokenHash,
      userId,
      createdAt,
      expiresAt,
    },
  })

  // Best-effort: attach metadata to user profile for auditing.
  try {
    await update({
      Key: userProfileKey(userId),
      UpdateExpression:
        'SET passwordResetRequestedAt = :t, passwordResetExpiresAt = :e, updatedAt = :u',
      ExpressionAttributeValues: {
        ':t': createdAt,
        ':e': expiresAt,
        ':u': nowIso(),
      },
    })
  } catch {}

  return { ok: true, token, expiresAt }
}

async function resetPasswordWithToken({ token, newPassword }) {
  const rawToken = String(token || '').trim()
  if (!rawToken) {
    const err = new Error('Invalid or expired reset token')
    err.code = 'invalid_token'
    throw err
  }

  const tokenHash = sha256Hex(rawToken)
  const tokenKey = resetTokenKey(tokenHash)
  const { Item } = await get({ Key: tokenKey })
  const rec = Item || null
  const now = nowIso()

  if (!rec || rec.expiresAt <= now || rec.usedAt) {
    const err = new Error('Invalid or expired reset token')
    err.code = 'invalid_token'
    throw err
  }

  const userId = rec.userId
  const passwordHash = await bcrypt.hash(String(newPassword), 12)

  // Use a transaction so a token can only be used once.
  await transactWrite({
    TransactItems: [
      {
        Update: {
          TableName: getTableName(),
          Key: tokenKey,
          UpdateExpression: 'SET usedAt = :u',
          ConditionExpression:
            'attribute_not_exists(usedAt) AND expiresAt > :u',
          ExpressionAttributeValues: { ':u': now },
        },
      },
      {
        Update: {
          TableName: getTableName(),
          Key: userProfileKey(userId),
          UpdateExpression:
            'SET passwordHash = :p, passwordResetCompletedAt = :u, updatedAt = :u REMOVE passwordResetExpiresAt',
          ExpressionAttributeValues: { ':p': passwordHash, ':u': now },
        },
      },
    ],
  })

  // Return the same login behavior as signup/login (issue a new JWT).
  const user = await getUserById(userId)
  const jwtToken = jwt.sign(
    { userId, username: user?.username || '' },
    jwtSecret(),
    { expiresIn: jwtExpire() },
  )

  return { ok: true, token: jwtToken }
}

module.exports = {
  getUserById,
  getUserIdByUsernameOrEmail,
  createUser,
  verifyLogin,
  requestPasswordReset,
  resetPasswordWithToken,
}
