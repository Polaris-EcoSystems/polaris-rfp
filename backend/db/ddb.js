const { DynamoDBClient } = require('@aws-sdk/client-dynamodb')
const {
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  UpdateCommand,
  DeleteCommand,
  QueryCommand,
  ScanCommand,
  TransactWriteCommand,
} = require('@aws-sdk/lib-dynamodb')

function getTableName() {
  const name = String(process.env.DDB_TABLE_NAME || '').trim()
  if (!name) {
    throw new Error('Missing DDB_TABLE_NAME env var')
  }
  return name
}

function getRegion() {
  return (
    process.env.AWS_REGION ||
    process.env.AWS_DEFAULT_REGION ||
    process.env.DDB_REGION ||
    'us-east-1'
  )
}

function getEndpoint() {
  const v = String(
    process.env.DDB_ENDPOINT || process.env.DYNAMODB_ENDPOINT || '',
  ).trim()
  return v || null
}

function getClientConfig() {
  const region = getRegion()
  const endpoint = getEndpoint()
  const cfg = { region }

  if (endpoint) {
    cfg.endpoint = endpoint
    // DynamoDB Local / custom endpoints usually run without AWS auth,
    // but the SDK still requires credentials to be present.
    if (!process.env.AWS_ACCESS_KEY_ID && !process.env.AWS_SECRET_ACCESS_KEY) {
      cfg.credentials = { accessKeyId: 'local', secretAccessKey: 'local' }
    }
  }

  return cfg
}

const client = new DynamoDBClient(getClientConfig())
const ddb = DynamoDBDocumentClient.from(client, {
  marshallOptions: { removeUndefinedValues: true },
})

async function get(params) {
  const TableName = getTableName()
  return await ddb.send(new GetCommand({ TableName, ...params }))
}

async function put(params) {
  const TableName = getTableName()
  return await ddb.send(new PutCommand({ TableName, ...params }))
}

async function update(params) {
  const TableName = getTableName()
  return await ddb.send(new UpdateCommand({ TableName, ...params }))
}

async function del(params) {
  const TableName = getTableName()
  return await ddb.send(new DeleteCommand({ TableName, ...params }))
}

async function query(params) {
  const TableName = getTableName()
  return await ddb.send(new QueryCommand({ TableName, ...params }))
}

async function scan(params) {
  const TableName = getTableName()
  return await ddb.send(new ScanCommand({ TableName, ...params }))
}

async function transactWrite(params) {
  return await ddb.send(new TransactWriteCommand(params))
}

module.exports = {
  ddb,
  getTableName,
  getRegion,
  getEndpoint,
  get,
  put,
  update,
  del,
  query,
  scan,
  transactWrite,
}
