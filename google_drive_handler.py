import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configuración de logging
logger = logging.getLogger(__name__)

# Si se modifica este ámbito, se debe eliminar el archivo token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GDriveHandler:
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Autenticación con Google Drive API."""
        creds = None
        # El archivo token.json almacena los tokens de acceso y actualización del usuario.
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        # Si no hay credenciales (válidas), permite al usuario iniciar sesión.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"❌ ARCHIVO NO ENCONTRADO: '{self.credentials_path}'. Necesitas descargar este archivo de Google Cloud Console.")
                    return
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Guarda las credenciales para la próxima ejecución.
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())

        self.service = build('drive', 'v3', credentials=creds)
        logger.info("✅ Autenticado exitosamente con Google Drive.")

    def upload_file(self, file_path, folder_id=None):
        """Sube un archivo a Google Drive."""
        if not self.service:
            logger.error("No se puede subir el archivo: No hay servicio de Drive activo.")
            return None

        file_metadata = {'name': os.path.basename(file_path)}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(file_path, mimetype='image/png')
        
        try:
            file = self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            file_id = file.get('id')
            logger.info(f"🚀 Archivo subido exitosamente. ID: {file_id}")
            return file_id
        except Exception as e:
            logger.error(f"❌ Error al subir archivo a Drive: {e}")
            return None

    def create_folder(self, folder_name):
        """Crea una carpeta en Google Drive y retorna el ID."""
        if not self.service:
            return None
            
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        try:
            folder = self.service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
            logger.info(f"📂 Carpeta creada: '{folder_name}' (ID: {folder_id})")
            return folder_id
        except Exception as e:
            logger.error(f"❌ Error al crear carpeta: {e}")
            return None

if __name__ == "__main__":
    # Inicialización rápida para generar el token.json
    logging.basicConfig(level=logging.INFO)
    logger.info("Iniciando proceso de autenticación...")
    handler = GDriveHandler()
    if handler.service:
        logger.info("✅ ¡Autenticación completada y token guardado!")
