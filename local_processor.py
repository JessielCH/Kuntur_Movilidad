import os
import sys
import time
import json
import re
import traceback
import logging
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

# Configurar entorno antes de cualquier import
os.environ['ULTRALYTICS_AUTOUPDATE'] = 'disabled'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# Configuración actualizada de Backblaze
B2_KEY_ID = os.getenv("B2_KEY_ID", "005edb6e50f32700000000003")
B2_APP_KEY = os.getenv("B2_APP_KEY", "K005P0f0Ubgb5zP7aFezbKC/6ri7l0Y")
B2_BUCKET_ID = os.getenv("B2_BUCKET_ID", "3e5dfb167e65e0af93720710")

# Rutas locales
CARPETA_VIDEOS = "./data/videos"
CARPETA_PROCESADOS = "./data/procesados"
CARPETA_POR_TRANSCRIBIR = "./data/por_transcribir"  # Nueva carpeta para audio

# Importar después de configurar el entorno
from utils.video_processing import procesar_video
from utils.backblaze_utils import subir_video_b2
from utils.audio_utils import procesar_audio  # Nueva utilidad para audio


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

    # Guardar resultados JSON
    nombre_base = os.path.basename(video_path).rsplit('.', 1)[0]
    json_salida = os.path.join(CARPETA_PROCESADOS, f"{nombre_base}.json")
    with open(json_salida, 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)
    logger.info(f"Resultados guardados en: {json_salida}")

    # Subir a Backblaze si hay alertas
    video_subido = False
    if resultados.get("alertas"):
        nombre_limpio = re.sub(r'[^a-zA-Z0-9_\-]', '_', nombre_base)
        nombre_evidencia = f"evidencia_kuntur_{nombre_limpio}.mp4"

        try:
            logger.info(f"Intentando subir: {video_procesado} como {nombre_evidencia}")
            subido = subir_video_b2(
                video_procesado,
                nombre_evidencia,
                B2_KEY_ID,
                B2_APP_KEY,
                B2_BUCKET_ID
            )
            if subido:
                logger.info(f"¡Video subido a Backblaze como {nombre_evidencia}!")
                video_subido = True
        except Exception as e:
            logger.error(f"Error subiendo a Backblaze: {str(e)}")

    # Mover archivos a carpeta procesados
    try:
        # Mover video procesado
        destino_procesado = os.path.join(CARPETA_PROCESADOS, os.path.basename(video_procesado))
        os.rename(video_procesado, destino_procesado)

        # Mover video original
        destino_original = os.path.join(CARPETA_PROCESADOS, os.path.basename(video_path))
        os.rename(video_path, destino_original)
        logger.info(f"Archivos movidos a: {CARPETA_PROCESADOS}")

        # Si hay alertas y el video se subió, procesar audio
        if resultados.get("alertas") and video_subido:
            # Mover video original a carpeta para transcripción
            os.makedirs(CARPETA_POR_TRANSCRIBIR, exist_ok=True)
            destino_transcribir = os.path.join(CARPETA_POR_TRANSCRIBIR, os.path.basename(video_path))
            os.rename(destino_original, destino_transcribir)

            # Procesar audio
            procesar_audio(destino_transcribir, json_salida)
    except Exception as e:
        logger.error(f"Error moviendo archivos: {str(e)}")


if __name__ == "__main__":
    # Crear carpetas si no existen
    os.makedirs(CARPETA_VIDEOS, exist_ok=True)
    os.makedirs(CARPETA_PROCESADOS, exist_ok=True)
    os.makedirs(CARPETA_POR_TRANSCRIBIR, exist_ok=True)  # Nueva carpeta

    # Iniciar monitorización
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