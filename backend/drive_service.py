"""
FaceFind Google Drive Integration
Handles OAuth2 authentication, image listing, downloading, and sync operations.
"""
import io
import os
import logging
from pathlib import Path
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from config import CREDENTIALS_PATH, TOKEN_PATH, SCOPES, DRIVE_FOLDER_ID

logger = logging.getLogger(__name__)


class DriveService:
    """Google Drive API wrapper for image operations."""

    def __init__(self):
        self.service = None
        self.folder_id = DRIVE_FOLDER_ID

    def authenticate(self) -> bool:
        """
        Authenticate with Google Drive API using OAuth2.
        First run opens browser for consent. Subsequent runs use saved token.
        Returns True if authentication succeeds.
        """
        creds = None

        # Load existing token
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")

        # Refresh or create new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None

            if not creds:
                if not os.path.exists(CREDENTIALS_PATH):
                    logger.error(
                        f"credentials.json not found at {CREDENTIALS_PATH}. "
                        "Please download it from Google Cloud Console."
                    )
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for future use
            token_dir = Path(TOKEN_PATH).parent
            token_dir.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())

        self.service = build("drive", "v3", credentials=creds)
        logger.info("Google Drive authenticated successfully")
        return True

    def list_images(self, folder_id: str = None, page_token: str = None,
                    modified_after: str = None) -> tuple[list[dict], str | None]:
        """
        List image files in a Drive folder with pagination.

        Args:
            folder_id: Drive folder ID (defaults to configured folder)
            page_token: Token for next page of results
            modified_after: ISO timestamp to filter recently modified files

        Returns:
            Tuple of (list of file metadata dicts, next_page_token or None)
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        fid = folder_id or self.folder_id
        query_parts = [
            f"'{fid}' in parents",
            "mimeType contains 'image/'",
            "trashed = false"
        ]

        if modified_after:
            query_parts.append(f"modifiedTime > '{modified_after}'")

        query = " and ".join(query_parts)

        try:
            results = self.service.files().list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, mimeType, webContentLink, thumbnailLink, modifiedTime)",
                pageToken=page_token,
                orderBy="modifiedTime desc"
            ).execute()

            files = results.get("files", [])
            next_token = results.get("nextPageToken")

            logger.info(f"Listed {len(files)} images (page_token={'yes' if next_token else 'no'})")
            return files, next_token

        except HttpError as e:
            logger.error(f"Drive API error listing images: {e}")
            raise

    def list_all_images(self, folder_id: str = None,
                        modified_after: str = None) -> list[dict]:
        """
        List ALL image files in a folder (handles pagination automatically).

        Returns:
            Complete list of file metadata dicts.
        """
        all_files = []
        page_token = None

        while True:
            files, page_token = self.list_images(
                folder_id=folder_id,
                page_token=page_token,
                modified_after=modified_after
            )
            all_files.extend(files)

            if not page_token:
                break

        logger.info(f"Total images found: {len(all_files)}")
        return all_files

    def download_image(self, file_id: str) -> bytes:
        """
        Download an image file by its Drive file ID.

        Returns:
            Raw image bytes.
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            request = self.service.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            buffer.seek(0)
            return buffer.read()

        except HttpError as e:
            logger.error(f"Drive API error downloading {file_id}: {e}")
            raise

    def get_file_metadata(self, file_id: str) -> dict:
        """Get metadata for a specific file."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            return self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, webContentLink, thumbnailLink, modifiedTime, size"
            ).execute()
        except HttpError as e:
            logger.error(f"Drive API error getting metadata for {file_id}: {e}")
            raise

    def get_thumbnail_url(self, file_id: str, size: int = 400) -> str:
        """
        Generate a thumbnail URL for an image.
        Uses Drive's built-in thumbnail generation.
        """
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=s{size}"

    def get_view_url(self, file_id: str) -> str:
        """Generate a view URL for an image."""
        return f"https://drive.google.com/uc?id={file_id}&export=view"
