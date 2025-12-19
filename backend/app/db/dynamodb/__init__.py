"""Shared DynamoDB utilities.

This package centralizes:
- boto3 client/resource configuration
- retry/backoff policy
- cursor pagination token encoding/decoding
- typed, expressive errors for consistent HTTP problem responses
- transactional helpers

"""

