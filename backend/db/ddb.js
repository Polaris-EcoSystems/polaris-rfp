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

const client = new DynamoDBClient({ region: getRegion() })
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
  get,
  put,
  update,
  del,
  query,
  scan,
  transactWrite,
}
