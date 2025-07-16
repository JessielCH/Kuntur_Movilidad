import os
import requests
import hashlib
import logging
import time

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def obtener_token_acceso(key_id, app_key):
    """Obtiene token de acceso usando el endpoint correcto"""
    auth_url = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
    try:
        logger.info(f"Autenticando con Backblaze usando keyID: {key_id[:5]}...")
        response = requests.get(auth_url, auth=(key_id, app_key), timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error de autenticación: {str(e)}")
        if 'response' in locals():
            logger.error(f"Respuesta del servidor: {response.status_code} - {response.text[:200]}")
        return None


def subir_video_b2(video_path, nombre_archivo, key_id, app_key, bucket_id):
    """
    Sube un video a Backblaze B2 usando el bucket ID directamente
    :return: True si la subida fue exitosa, False en caso contrario
    """
    # 1. Autenticación
    auth_data = obtener_token_acceso(key_id, app_key)
    if not auth_data:
        return False

    # 2. Obtener URL de subida
    try:
        upload_url_endpoint = f"{auth_data['apiUrl']}/b2api/v2/b2_get_upload_url"
        headers = {"Authorization": auth_data["authorizationToken"]}
        payload = {"bucketId": bucket_id}

        logger.info(f"Obteniendo URL de subida desde: {upload_url_endpoint}")
        response = requests.post(upload_url_endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        upload_data = response.json()
        logger.info(f"URL de subida obtenida: {upload_data['uploadUrl']}")
    except Exception as e:
        logger.error(f"Error obteniendo URL de subida: {str(e)}")
        return False

    # 3. Preparar y subir archivo
    try:
        # Leer archivo
        file_size = os.path.getsize(video_path)
        logger.info(f"Tamaño del archivo: {file_size / 1024 / 1024:.2f} MB")

        with open(video_path, 'rb') as f:
            file_data = f.read()

        # Calcular SHA1
        sha1 = hashlib.sha1(file_data).hexdigest()

        # Cabeceras
        upload_headers = {
            "Authorization": upload_data["authorizationToken"],
            "Content-Type": "application/octet-stream",
            "X-Bz-File-Name": nombre_archivo,
            "X-Bz-Content-Sha1": sha1,
            "Content-Length": str(file_size)
        }

        # 4. Subir
        logger.info(f"Subiendo {os.path.basename(video_path)}...")
        start_time = time.time()
        response = requests.post(
            upload_data["uploadUrl"],
            headers=upload_headers,
            data=file_data,
            timeout=120  # Tiempo mayor para videos grandes
        )
        response.raise_for_status()
        elapsed = time.time() - start_time

        logger.info(
            f"✅ Video subido exitosamente: {nombre_archivo} ({file_size / 1024 / 1024:.2f} MB en {elapsed:.1f}s)")
        return True

    except Exception as e:
        logger.error(f"Error en subida: {str(e)}")
        return False


def download_file_from_bucket(key_id, app_key, file_id, local_path):
    """Descargar archivo desde Backblaze B2"""
    try:
        auth_data = obtener_token_acceso(key_id, app_key)
        if not auth_data:
            return False

        download_url = f"{auth_data['downloadUrl']}/b2api/v2/b2_download_file_by_id?fileId={file_id}"
        headers = {"Authorization": auth_data["authorizationToken"]}

        logger.info(f"Descargando archivo ID: {file_id}")
        start_time = time.time()
        response = requests.get(download_url, headers=headers, stream=True, timeout=30)
        if response.status_code != 200:
            logger.error(f"Error descargando archivo: {response.status_code} - {response.text}")
            return False

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = os.path.getsize(local_path)
        elapsed = time.time() - start_time
        logger.info(f"✅ Archivo descargado: {local_path} ({file_size / 1024 / 1024:.2f} MB en {elapsed:.1f}s)")
        return True

    except Exception as e:
        logger.error(f"Error en descarga: {str(e)}")
        return False