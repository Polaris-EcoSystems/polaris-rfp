# Google Drive Integration

## Overview

Full CRUDL (Create, Read, Update, Delete, List) integration with Google Drive. Agents can create, read, update, delete, and list Google Docs, folders, and files. The integration uses AWS Secrets Manager to securely retrieve Google API credentials.

## Tools Added

### CRUDL Operations

**Create:**

- `google_create_doc` - Create new Google Docs
- `google_create_folder` - Create folders
- `google_upload_file` - Upload files

**Read:**

- `google_read_doc` - Read Google Docs content

**Update:**

- `google_update_doc` - Update document content/title
- `google_update_metadata` - Rename/move files

**Delete:**

- `google_delete_file` - Delete files/folders (trash or permanent)

**List:**

- `google_list_drive_files` - List files and folders

## Detailed Tool Reference

### 1. `secrets_get_value`

Get secret values from AWS Secrets Manager.

**Features:**

- ECS task has permissions to access any secret
- Google secrets (GOOGLE_API_KEY, GOOGLE_CREDENTIALS) are automatically allowed
- Can parse JSON secrets automatically
- Falls back to string if not JSON

**Usage:**

```python
secrets_get_value(
    secretId="arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_API_KEY-yPu460",
    parseJson=True
)
```

### 2. `google_read_doc`

Read content from a Google Doc.

**Features:**

- Accepts Google Docs URLs or document IDs
- Automatically extracts document ID from URLs
- Uses service account credentials (with API key fallback)
- Exports Google Docs as plain text
- Returns metadata (title, created/modified times, etc.)

**Usage:**

```python
google_read_doc(
    url="https://docs.google.com/document/d/14-58bKRlJ3B4GOLfgGw8yk3QGXp5KUG5-VliJIGSlWQ/edit"
)
# or
google_read_doc(
    documentId="14-58bKRlJ3B4GOLfgGw8yk3QGXp5KUG5-VliJIGSlWQ"
)
```

**Response:**

```json
{
  "ok": true,
  "documentId": "14-58bKRlJ3B4GOLfgGw8yk3QGXp5KUG5-VliJIGSlWQ",
  "title": "Document Title",
  "content": "Full text content of the document...",
  "mimeType": "application/vnd.google-apps.document",
  "createdTime": "2024-12-19T...",
  "modifiedTime": "2024-12-19T...",
  "webViewLink": "https://docs.google.com/..."
}
```

### 3. `google_create_doc`

Create a new Google Doc.

**Features:**

- Create documents with title
- Set initial content
- Optionally place in specific folder

**Usage:**

```python
google_create_doc(
    title="My Document",
    content="Initial content here...",
    folderId="optional_folder_id"
)
```

**Response:**

```json
{
  "ok": true,
  "documentId": "14-58bKRlJ3B4GOLfgGw8yk3QGXp5KUG5-VliJIGSlWQ",
  "title": "My Document",
  "webViewLink": "https://docs.google.com/...",
  "createdTime": "2024-12-19T..."
}
```

### 4. `google_create_folder`

Create a new folder in Google Drive.

**Usage:**

```python
google_create_folder(
    name="My Folder",
    parentFolderId="optional_parent_folder_id"
)
```

### 5. `google_upload_file`

Upload a file to Google Drive.

**Features:**

- Upload text or binary files
- Auto-detects MIME type from filename
- Supports any file type

**Usage:**

```python
google_upload_file(
    name="report.pdf",
    content="<base64_encoded_content>",
    mimeType="application/pdf",
    folderId="optional_folder_id"
)
```

### 6. `google_update_doc`

Update a Google Doc (content and/or title).

**Features:**

- Replace entire document content
- Update title
- Can update both or just one

**Usage:**

```python
google_update_doc(
    documentId="14-58bKRlJ3B4GOLfgGw8yk3QGXp5KUG5-VliJIGSlWQ",
    content="New content...",
    title="Updated Title"
)
```

### 7. `google_update_metadata`

Update file metadata (rename, move).

**Usage:**

```python
google_update_metadata(
    fileId="file_id",
    name="New Name",
    folderId="new_parent_folder_id"  # Moves file
)
```

### 8. `google_delete_file`

Delete a file or folder.

**Features:**

- Move to trash (default, recoverable)
- Permanent delete (optional, cannot be recovered)

**Usage:**

```python
# Move to trash
google_delete_file(
    fileId="file_id",
    permanent=False
)

# Permanent delete
google_delete_file(
    fileId="file_id",
    permanent=True
)
```

### 9. `google_list_drive_files`

List files in Google Drive.

**Features:**

- Optionally filter by folder ID
- Returns file metadata (name, ID, mimeType, size, etc.)
- Configurable limit

**Usage:**

```python
google_list_drive_files(
    folderId="optional_folder_id",
    limit=50
)
```

## Credentials

The integration uses two secrets from AWS Secrets Manager:

1. **GOOGLE_API_KEY** (`arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_API_KEY-yPu460`)

   - Simple API key string
   - Used as fallback if service account fails

2. **GOOGLE_CREDENTIALS** (`arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_CREDENTIALS-lqF0A9`)
   - Service account JSON credentials
   - Preferred method (more permissions)
   - Includes OAuth scopes for Drive read access

## Implementation Details

### File Structure

```
backend/app/tools/categories/
├── aws/
│   └── aws_secrets.py          # Added get_secret_value()
└── google/
    ├── __init__.py
    └── google_drive.py         # New Google Drive tools
```

### Dependencies

Added to `requirements.txt`:

- `google-api-python-client==2.152.0`
- `google-auth==2.35.0`
- `google-auth-oauthlib==1.2.1`
- `google-auth-httplib2==0.2.0`

### Security

- Credentials are fetched from Secrets Manager on-demand
- Service account credentials preferred (more secure)
- API key used as fallback only
- All secrets access is logged
- Google secrets automatically allowed (no allowlist restriction)

## Example Agent Usage

### Reading Documents

```
User: "@Polaris RFP review these docs and critique them."
[User provides Google Docs URLs]

Agent: [Calls google_read_doc for each URL]
Agent: [Gets full document content]
Agent: [Performs analysis and critique]
Agent: [Returns structured review]
```

### Creating Documents

```
User: "@Polaris RFP create a draft CSO document for the Infrastructure project"

Agent: [Calls google_create_doc with title and content]
Agent: [Returns document link]
Agent: "I've created the draft CSO document: [link]"
```

### Updating Documents

```
User: "@Polaris RFP update the CSO document with the new requirements"

Agent: [Calls google_read_doc to get current content]
Agent: [Modifies content]
Agent: [Calls google_update_doc with new content]
Agent: "Updated the document with new requirements"
```

### Organizing Files

```
User: "@Polaris RFP organize all CSO drafts into a folder"

Agent: [Calls google_create_folder(name="CSO Drafts")]
Agent: [Calls google_list_drive_files to find CSO documents]
Agent: [Calls google_update_metadata to move each to folder]
Agent: "Organized all CSO drafts into 'CSO Drafts' folder"
```

## Discovery

All tools are automatically discoverable via the capability introspection system:

```python
# Agent can discover available tools
list_capabilities(category="tool", subcategory="google")

# Agent can get full details
introspect_capability(name="google_read_doc")
```

## Error Handling

- Invalid URLs/document IDs return clear error messages
- API errors are logged and returned to agent
- Graceful fallback from service account to API key
- Non-Google Doc files return appropriate error

## Permissions & Scopes

The integration uses full Drive API scope (`https://www.googleapis.com/auth/drive`) to enable all CRUDL operations. Service account credentials are required for write operations (create, update, delete).

## Error Handling

- Invalid file/document IDs return clear error messages
- API errors are logged and returned to agent
- Graceful fallback from service account to API key (for read operations only)
- Non-Google Doc files return appropriate error for doc-specific operations
- Trash operations are recoverable (unless permanent delete)

## Future Enhancements

- Support for Google Sheets (read/write as CSV/JSON)
- Support for Google Slides (read/export)
- Advanced search and filtering
- Sharing management (add/remove permissions)
- Document comments and suggestions
- Version history access
- Batch operations
