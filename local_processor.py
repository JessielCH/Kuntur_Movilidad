import os
import sys
import time
import json
import re
import traceback
import logging
import threading
import shutil
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("local_processor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configurar entorno
os.environ['ULTRALYTICS_AUTOUPDATE'] = 'disabled'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# Configuración Backblaze
B2_KEY_ID = os.getenv("B2_KEY_ID", "005edb6e50f32700000000003")
B2_APP_KEY = os.getenv("B2_APP_KEY", "K005P0f0Ubgb5zP7aFezbKC/6ri7l0Y")
B2_BUCKET_ID = os.getenv("B2_BUCKET_ID", "3e5dfb167e65e0af93720710")

# Rutas locales
CARPETA_VIDEOS = "./data/videos"
CARPETA_PROCESADOS = "./data/procesados"

# Importar utilidades
from utils.video_processing import procesar_video
from utils.backblaze_utils import subir_video_b2
from utils.audio_utils import procesar_audio
from utils.db_utils import get_user_data


class VideoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
            logger.info(f"\nNuevo video detectado: {event.src_path}")
            try:
                time.sleep(2)  # Esperar a que el archivo esté completamente escrito
                procesar_video_local(event.src_path)
            except Exception as e:
                logger.error(f"Error procesando video: {str(e)}")
                logger.error(traceback.format_exc())


def procesar_video_local(video_path):
    # Procesar video
    resultados, video_procesado = procesar_video(video_path)

    if not resultados or "error" in resultados:
        logger.error("Error en procesamiento de video")
        return

    # Extraer username del filename: usuario@timestamp.mp4
    video_filename = os.path.basename(video_path)
    nombre_base = video_filename.rsplit('.', 1)[0]
    username = nombre_base.split("@")[0] if "@" in nombre_base else "unknown"

    # Obtener datos de usuario desde la base de datos
    user_data = get_user_data(username) or {}
    unidad = user_data.get("unidad", "desconocida")
    chofer = user_data.get("chofer", "desconocido")

    # Crear estructura de carpetas: usuario/unidad/fecha
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    hora_actual = datetime.now().strftime("%H-%M-%S")
    estructura_carpeta = os.path.join(CARPETA_PROCESADOS, username, unidad, fecha_actual)
    os.makedirs(estructura_carpeta, exist_ok=True)

    # Manejar videos con alertas
    if resultados.get("alertas"):
        # Crear nombre estructurado
        nombre_evidencia = f"{hora_actual}.mp4"
        b2_path = f"{username}/{unidad}/{fecha_actual}/{nombre_evidencia}"

        # Subir a Backblaze
        try:
            logger.info(f"Subiendo video a Backblaze: {b2_path}")
            subido = subir_video_b2(
                video_procesado,
                b2_path,
                B2_KEY_ID,
                B2_APP_KEY,
                B2_BUCKET_ID
            )
            if subido:
                logger.info(f"¡Video subido a Backblaze como {b2_path}!")
            else:
                logger.error("Error al subir video a Backblaze")
        except Exception as e:
            logger.error(f"Error subiendo a Backblaze: {str(e)}")

        # Mover archivos a carpeta estructurada
        try:
            # Mover video procesado
            destino_procesado = os.path.join(estructura_carpeta, f"{hora_actual}_procesado.mp4")
            shutil.move(video_procesado, destino_procesado)

            # Mover video original
            destino_original = os.path.join(estructura_carpeta, nombre_evidencia)
            shutil.move(video_path, destino_original)
            logger.info(f"Archivos movidos a: {estructura_carpeta}")

            # Procesar audio y generar JSON final
            procesar_audio(destino_original, resultados, username, nombre_evidencia, b2_path)
        except Exception as e:
            logger.error(f"Error moviendo archivos: {str(e)}")
    else:
        # Eliminar videos sin alertas
        try:
            os.remove(video_path)
            os.remove(video_procesado)
            logger.info("Videos sin alertas eliminados")
        except Exception as e:
            logger.error(f"Error eliminando videos: {str(e)}")


# Nueva función de limpieza automática
def limpieza_automatica():
    while True:
        logger.info("Ejecutando limpieza automática...")
        try:
            # Limpiar solo carpeta de videos (los procesados se mantienen)
            for filename in os.listdir(CARPETA_VIDEOS):
                file_path = os.path.join(CARPETA_VIDEOS, filename)
                if os.path.isfile(file_path):
                    file_age = time.time() - os.path.getmtime(file_path)
                    if file_age > 600:  # 10 minutos
                        os.remove(file_path)
                        logger.info(f"Borrado: {file_path}")
        except Exception as e:
            logger.error(f"Error en limpieza: {str(e)}")
        time.sleep(600)  # Esperar 10 minutos


if __name__ == "__main__":
    # Crear carpetas si no existen
    os.makedirs(CARPETA_VIDEOS, exist_ok=True)
    os.makedirs(CARPETA_PROCESADOS, exist_ok=True)
    os.makedirs(os.path.join("data", "frames"), exist_ok=True)

    # Iniciar hilo de limpieza automática
    cleaner = threading.Thread(target=limpieza_automatica, daemon=True)
    cleaner.start()

    # Iniciar monitorización de nuevos videos
    event_handler = VideoHandler()
    observer = Observer()
    observer.schedule(event_handler, CARPETA_VIDEOS, recursive=False)
    observer.start()

    logger.info(f"Monitoreando carpeta {CARPETA_VIDEOS}...")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()