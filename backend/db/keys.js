function nowIso() {
  return new Date().toISOString()
}

function normalizeEmail(email) {
  return String(email || '').trim().toLowerCase()
}

function normalizeUsername(username) {
  return String(username || '').trim().toLowerCase()
}

function userPk(userId) {
  return `USER#${String(userId)}`
}

function userProfileKey(userId) {
  return { pk: userPk(userId), sk: 'PROFILE' }
}

function usernameUniqueKey(usernameLower) {
  return { pk: `USERNAME#${String(usernameLower)}`, sk: 'UNIQUE' }
}

function emailUniqueKey(emailLower) {
  return { pk: `EMAIL#${String(emailLower)}`, sk: 'UNIQUE' }
}

function typePk(type) {
  return `TYPE#${String(type)}`
}

module.exports = {
  nowIso,
  normalizeEmail,
  normalizeUsername,
  userPk,
  userProfileKey,
  usernameUniqueKey,
  emailUniqueKey,
  typePk,
}
