const crypto = require('crypto')

function newId(prefix = '') {
  const id = crypto.randomUUID()
  return prefix ? `${prefix}_${id}` : id
}

module.exports = { newId }
