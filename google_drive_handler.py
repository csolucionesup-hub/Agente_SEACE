import os
import logging
import mimetypes
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GDriveHandler:
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Autenticación robusta con manejo de expiración."""
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"❌ Error al refrescar token: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"Falta '{self.credentials_path}' en el directorio raíz.")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())

        self.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        logger.info("✅ Conexión con Google Drive establecida.")

    def get_or_create_folder(self, folder_name):
        """Busca una carpeta existente o crea una nueva para evitar desorden."""
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        try:
            results = self.service.files().list(q=query, fields="files(id)").execute()
            folders = results.get('files', [])
            
            if folders:
                folder_id = folders[0]['id']
                logger.info(f"📁 Usando carpeta existente: '{folder_name}' (ID: {folder_id})")
                return folder_id
            
            return self.create_folder(folder_name)
        except Exception as e:
            logger.error(f"❌ Error al buscar/crear carpeta: {e}")
            return None

    def create_folder(self, folder_name):
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = self.service.files().create(body=file_metadata, fields='id').execute()
        folder_id = folder.get('id')
        logger.info(f"📂 Nueva carpeta creada: '{folder_name}' (ID: {folder_id})")
        return folder_id

    def upload_file(self, file_path, folder_id=None):
        """Sube archivos con detección automática de tipo."""
        if not os.path.exists(file_path):
            logger.warning(f"⚠️ El archivo local no existe: {file_path}")
            return None

        file_name = os.path.basename(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or 'application/octet-stream'

        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        
        try:
            file = self.service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id'
            ).execute()
            logger.info(f"🚀 {file_name} subido con éxito (ID: {file.get('id')})")
            return file.get('id')
        except Exception as e:
            logger.error(f"❌ Error crítico en subida a Drive: {e}")
            return None
