"""
Google Drive tools for reading Google Docs and accessing Drive files.
"""

from __future__ import annotations

import json
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ...registry.aws_clients import secretsmanager_client
from ...observability.logging import get_logger

log = get_logger("google_drive")


def _get_google_credentials(*, use_api_key: bool = False) -> Any:
    """
    Get Google credentials from Secrets Manager.
    
    Args:
        use_api_key: If True, use GOOGLE_API_KEY secret (simple API key).
                    If False, use GOOGLE_CREDENTIALS secret (service account JSON).
    
    Returns:
        Credentials object or API key string
    """
    if use_api_key:
        secret_arn = "arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_API_KEY-yPu460"
    else:
        secret_arn = "arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_CREDENTIALS-lqF0A9"
    
    try:
        sm = secretsmanager_client()
        resp = sm.get_secret_value(SecretId=secret_arn)
        secret_string = resp.get("SecretString")
        
        if not secret_string:
            raise ValueError("No secret value found")
        
        if use_api_key:
            # Simple API key string
            return secret_string.strip()
        else:
            # Service account JSON
            creds_dict = json.loads(secret_string)
            # Use full drive scope for CRUDL operations
            scopes = ['https://www.googleapis.com/auth/drive']
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=scopes
            )
            return credentials
    
    except Exception as e:
        log.error("get_google_credentials_failed", error=str(e), use_api_key=use_api_key)
        raise


def _extract_document_id(url: str) -> str | None:
    """
    Extract document ID from Google Docs URL.
    
    Supports formats:
    - https://docs.google.com/document/d/{id}/edit
    - https://docs.google.com/document/d/{id}/edit?usp=sharing
    - https://docs.google.com/document/d/{id}
    """
    if not url or not isinstance(url, str):
        return None
    
    url = url.strip()
    
    # Try to extract ID from /d/{id}/ pattern
    if "/d/" in url:
        parts = url.split("/d/")
        if len(parts) > 1:
            doc_id = parts[1].split("/")[0].split("?")[0].split("#")[0]
            if doc_id:
                return doc_id
    
    # If it looks like just an ID
    if len(url) > 10 and "/" not in url and " " not in url:
        return url
    
    return None


def read_google_doc(*, url: str | None = None, document_id: str | None = None) -> dict[str, Any]:
    """
    Read content from a Google Doc.
    
    Args:
        url: Google Docs URL (e.g., https://docs.google.com/document/d/.../edit)
        document_id: Direct document ID (alternative to URL)
    
    Returns:
        Dict with 'ok', 'content', 'title', 'documentId'
    """
    doc_id = document_id
    if not doc_id and url:
        doc_id = _extract_document_id(url)
    
    if not doc_id:
        return {"ok": False, "error": "document_id or valid url is required"}
    
    try:
        # Try service account credentials first
        try:
            credentials = _get_google_credentials(use_api_key=False)
            service = build('drive', 'v3', credentials=credentials)
        except Exception as e:
            log.warning("service_account_failed_trying_api_key", error=str(e))
            # Fallback to API key (limited functionality)
            api_key = _get_google_credentials(use_api_key=True)
            service = build('drive', 'v3', developerKey=api_key)
        
        # Get document metadata
        file_metadata = service.files().get(
            fileId=doc_id,
            fields='id,name,mimeType,createdTime,modifiedTime,webViewLink'
        ).execute()
        
        # Export as plain text
        # For Google Docs, we use the export endpoint
        if file_metadata.get('mimeType') == 'application/vnd.google-apps.document':
            # Export as plain text
            content = service.files().export_media(
                fileId=doc_id,
                mimeType='text/plain'
            ).execute()
            
            content_text = content.decode('utf-8') if isinstance(content, bytes) else str(content)
            
            return {
                "ok": True,
                "documentId": doc_id,
                "title": file_metadata.get('name', ''),
                "content": content_text,
                "mimeType": file_metadata.get('mimeType', ''),
                "createdTime": file_metadata.get('createdTime', ''),
                "modifiedTime": file_metadata.get('modifiedTime', ''),
                "webViewLink": file_metadata.get('webViewLink', ''),
            }
        else:
            return {
                "ok": False,
                "error": f"File is not a Google Doc (mimeType: {file_metadata.get('mimeType')})",
                "documentId": doc_id,
                "mimeType": file_metadata.get('mimeType', ''),
            }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_api_error", error=error_msg, document_id=doc_id)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("read_google_doc_failed", error=str(e), document_id=doc_id)
        return {"ok": False, "error": str(e)}


def list_google_drive_files(*, folder_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    """
    List files in Google Drive.
    
    Args:
        folder_id: Optional folder ID to list files from
        limit: Maximum number of files to return
    
    Returns:
        Dict with 'ok', 'files' (list of file metadata)
    """
    try:
        # Try service account credentials first
        try:
            credentials = _get_google_credentials(use_api_key=False)
            service = build('drive', 'v3', credentials=credentials)
        except Exception as e:
            log.warning("service_account_failed_trying_api_key", error=str(e))
            # Fallback to API key
            api_key = _get_google_credentials(use_api_key=True)
            service = build('drive', 'v3', developerKey=api_key)
        
        query = "trashed=false"
        if folder_id:
            query += f" and '{folder_id}' in parents"
        
        results = service.files().list(
            q=query,
            pageSize=min(limit, 100),
            fields='files(id,name,mimeType,createdTime,modifiedTime,webViewLink,size)'
        ).execute()
        
        files = results.get('files', [])
        
        return {
            "ok": True,
            "files": files,
            "count": len(files),
        }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_list_error", error=error_msg)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("list_google_drive_files_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def create_google_doc(*, title: str, content: str | None = None, folder_id: str | None = None) -> dict[str, Any]:
    """
    Create a new Google Doc.
    
    Args:
        title: Document title
        content: Optional initial content (plain text)
        folder_id: Optional folder ID to create document in
    
    Returns:
        Dict with 'ok', 'documentId', 'title', 'webViewLink'
    """
    if not title or not title.strip():
        return {"ok": False, "error": "title is required"}
    
    try:
        credentials = _get_google_credentials(use_api_key=False)
        service = build('drive', 'v3', credentials=credentials)
        
        # Create document metadata
        file_metadata = {
            'name': title.strip(),
            'mimeType': 'application/vnd.google-apps.document',
        }
        
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        # Create the document
        file = service.files().create(
            body=file_metadata,
            fields='id,name,webViewLink,createdTime'
        ).execute()
        
        doc_id = file.get('id')
        
        # If content provided, update the document
        if content and content.strip():
            try:
                # Import content using batchUpdate (requires Drive API v3 with documents API)
                from googleapiclient.discovery import build as build_docs
                docs_service = build_docs('docs', 'v1', credentials=credentials)
                
                # Insert text at the beginning
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        'requests': [
                            {
                                'insertText': {
                                    'location': {'index': 1},
                                    'text': content.strip()
                                }
                            }
                        ]
                    }
                ).execute()
            except Exception as e:
                log.warning("failed_to_set_initial_content", error=str(e))
                # Document created but content not set - that's okay
        
        return {
            "ok": True,
            "documentId": doc_id,
            "title": file.get('name', title),
            "webViewLink": file.get('webViewLink', ''),
            "createdTime": file.get('createdTime', ''),
        }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_create_doc_error", error=error_msg)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("create_google_doc_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def create_google_folder(*, name: str, parent_folder_id: str | None = None) -> dict[str, Any]:
    """
    Create a new folder in Google Drive.
    
    Args:
        name: Folder name
        parent_folder_id: Optional parent folder ID
    
    Returns:
        Dict with 'ok', 'folderId', 'name', 'webViewLink'
    """
    if not name or not name.strip():
        return {"ok": False, "error": "name is required"}
    
    try:
        credentials = _get_google_credentials(use_api_key=False)
        service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = {
            'name': name.strip(),
            'mimeType': 'application/vnd.google-apps.folder',
        }
        
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        
        file = service.files().create(
            body=file_metadata,
            fields='id,name,webViewLink,createdTime'
        ).execute()
        
        return {
            "ok": True,
            "folderId": file.get('id'),
            "name": file.get('name', name),
            "webViewLink": file.get('webViewLink', ''),
            "createdTime": file.get('createdTime', ''),
        }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_create_folder_error", error=error_msg)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("create_google_folder_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def upload_file_to_drive(
    *,
    name: str,
    content: bytes | str,
    mime_type: str | None = None,
    folder_id: str | None = None,
) -> dict[str, Any]:
    """
    Upload a file to Google Drive.
    
    Args:
        name: File name
        content: File content (bytes or string)
        mime_type: MIME type (e.g., 'text/plain', 'application/pdf')
        folder_id: Optional folder ID to upload to
    
    Returns:
        Dict with 'ok', 'fileId', 'name', 'webViewLink'
    """
    if not name or not name.strip():
        return {"ok": False, "error": "name is required"}
    
    if not content:
        return {"ok": False, "error": "content is required"}
    
    try:
        credentials = _get_google_credentials(use_api_key=False)
        service = build('drive', 'v3', credentials=credentials)
        
        # Convert string to bytes if needed
        if isinstance(content, str):
            content_bytes = content.encode('utf-8')
        else:
            content_bytes = content
        
        # Determine MIME type if not provided
        if not mime_type:
            if name.endswith('.txt'):
                mime_type = 'text/plain'
            elif name.endswith('.pdf'):
                mime_type = 'application/pdf'
            elif name.endswith('.json'):
                mime_type = 'application/json'
            else:
                mime_type = 'application/octet-stream'
        
        # File metadata
        file_metadata = {
            'name': name.strip(),
        }
        
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        # Upload file using MediaIoBaseUpload
        from io import BytesIO
        from googleapiclient.http import MediaIoBaseUpload
        
        media_body = MediaIoBaseUpload(
            BytesIO(content_bytes),
            mimetype=mime_type,
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id,name,webViewLink,createdTime,size'
        ).execute()
        
        return {
            "ok": True,
            "fileId": file.get('id'),
            "name": file.get('name', name),
            "webViewLink": file.get('webViewLink', ''),
            "createdTime": file.get('createdTime', ''),
            "size": file.get('size', len(content_bytes)),
        }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_upload_error", error=error_msg)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("upload_file_to_drive_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def update_google_doc(*, document_id: str, content: str | None = None, title: str | None = None) -> dict[str, Any]:
    """
    Update a Google Doc (content and/or title).
    
    Args:
        document_id: Document ID
        content: New content to append/replace (plain text)
        title: New title (optional)
    
    Returns:
        Dict with 'ok', 'documentId'
    """
    if not document_id:
        return {"ok": False, "error": "document_id is required"}
    
    try:
        credentials = _get_google_credentials(use_api_key=False)
        service = build('drive', 'v3', credentials=credentials)
        
        # Update title if provided
        if title and title.strip():
            service.files().update(
                fileId=document_id,
                body={'name': title.strip()},
                fields='id,name'
            ).execute()
        
        # Update content if provided
        if content and content.strip():
            from googleapiclient.discovery import build as build_docs
            docs_service = build_docs('docs', 'v1', credentials=credentials)
            
            # Get current document to find end index
            doc = docs_service.documents().get(documentId=document_id).execute()
            end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)
            
            # Clear existing content and insert new
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={
                    'requests': [
                        {
                            'deleteContentRange': {
                                'range': {
                                    'startIndex': 1,
                                    'endIndex': end_index - 1
                                }
                            }
                        },
                        {
                            'insertText': {
                                'location': {'index': 1},
                                'text': content.strip()
                            }
                        }
                    ]
                }
            ).execute()
        
        return {
            "ok": True,
            "documentId": document_id,
        }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_update_doc_error", error=error_msg)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("update_google_doc_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def update_file_metadata(
    *,
    file_id: str,
    name: str | None = None,
    folder_id: str | None = None,
    move_to_folder_id: str | None = None,
) -> dict[str, Any]:
    """
    Update file metadata (rename, move, change parent folder).
    
    Args:
        file_id: File ID
        name: New name (optional)
        folder_id: New parent folder ID (moves file)
        move_to_folder_id: Alias for folder_id (moves file to new folder)
    
    Returns:
        Dict with 'ok', 'fileId', 'name'
    """
    if not file_id:
        return {"ok": False, "error": "file_id is required"}
    
    try:
        credentials = _get_google_credentials(use_api_key=False)
        service = build('drive', 'v3', credentials=credentials)
        
        # Determine target folder
        target_folder = move_to_folder_id or folder_id
        
        # Get current file to check existing parents
        file = service.files().get(
            fileId=file_id,
            fields='id,name,parents'
        ).execute()
        
        # Prepare update body
        update_body: dict[str, Any] = {}
        if name and name.strip():
            update_body['name'] = name.strip()
        
        # Handle folder move
        if target_folder:
            previous_parents = ",".join(file.get('parents', []))
            update_body['addParents'] = target_folder
            update_body['removeParents'] = previous_parents
        
        if update_body:
            updated_file = service.files().update(
                fileId=file_id,
                body=update_body,
                fields='id,name,parents'
            ).execute()
            
            return {
                "ok": True,
                "fileId": file_id,
                "name": updated_file.get('name', name or file.get('name', '')),
            }
        else:
            return {
                "ok": True,
                "fileId": file_id,
                "name": file.get('name', ''),
            }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_update_metadata_error", error=error_msg)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("update_file_metadata_failed", error=str(e))
        return {"ok": False, "error": str(e)}


def delete_google_file(*, file_id: str, permanent: bool = False) -> dict[str, Any]:
    """
    Delete a file or folder from Google Drive.
    
    Args:
        file_id: File or folder ID
        permanent: If True, permanently delete (cannot be recovered). If False, move to trash.
    
    Returns:
        Dict with 'ok', 'fileId'
    """
    if not file_id:
        return {"ok": False, "error": "file_id is required"}
    
    try:
        credentials = _get_google_credentials(use_api_key=False)
        service = build('drive', 'v3', credentials=credentials)
        
        if permanent:
            service.files().delete(fileId=file_id).execute()
        else:
            # Move to trash
            service.files().update(
                fileId=file_id,
                body={'trashed': True}
            ).execute()
        
        return {
            "ok": True,
            "fileId": file_id,
            "permanent": permanent,
        }
    
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8')) if e.content else {}
        error_msg = error_details.get('error', {}).get('message', str(e))
        log.error("google_drive_delete_error", error=error_msg)
        return {"ok": False, "error": f"Google Drive API error: {error_msg}"}
    
    except Exception as e:
        log.error("delete_google_file_failed", error=str(e))
        return {"ok": False, "error": str(e)}
