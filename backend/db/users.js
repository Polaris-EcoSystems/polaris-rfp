const bcrypt = require('bcryptjs')
const jwt = require('jsonwebtoken')
const { get, transactWrite, update, getTableName } = require('./ddb')
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
  return process.env.JWT_SECRET || 'your-secret-key'
}

function jwtExpire() {
  return process.env.JWT_EXPIRE || '24h'
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

module.exports = {
  getUserById,
  getUserIdByUsernameOrEmail,
  createUser,
  verifyLogin,
}
