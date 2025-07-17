import os
import time
import json
import requests
import subprocess
import logging
import ssl  # Importar el módulo ssl
import certifi  # Importar certifi
from datetime import datetime
from PIL import Image
from transformers import pipeline
from faster_whisper import WhisperModel
from utils.llm_utils import generar_descripcion_enriquecida
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar modelos
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
blip_pipe = pipeline("image-to-text", model="Salesforce/blip-image-captioning-base")

# Configurar MongoDB
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "kuntur_db")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "alertas")


def conectar_mongodb():
    """Conectar a MongoDB Atlas"""
    if not MONGO_URI:
        logger.warning("No se configuró MONGO_URI")
        return None

    try:
        # Intento 1: Con certificados actualizados
        client = MongoClient(
            MONGO_URI,
            tlsCAFile=certifi.where(),
            server_api=ServerApi('1')
        )
        client.admin.command('ping')
        logger.info("Conexión exitosa a MongoDB Atlas")
        return client
    except Exception as e:
        logger.error(f"Error conectando a MongoDB con certificados: {e}")

        try:
            # Intento 2: Sin verificación SSL (solo para desarrollo)
            client = MongoClient(
                MONGO_URI,
                ssl=True,
                ssl_cert_reqs=ssl.CERT_NONE,
                server_api=ServerApi('1')
            )
            client.admin.command('ping')
            logger.warning("Conexión exitosa sin verificación SSL")
            return client
        except Exception as e2:
            logger.error(f"Error en conexión alternativa: {e2}")
            return None


def guardar_en_mongodb(data):
    """Guardar documento en MongoDB"""
    client = conectar_mongodb()
    if not client:
        logger.warning("No se pudo conectar a MongoDB, omitiendo guardado")
        return False

    try:
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        result = collection.insert_one(data)
        logger.info(f"Datos guardados en MongoDB: {result.inserted_id}")
        return True
    except Exception as e:
        logger.error(f"Error guardando en MongoDB: {e}")
        return False
    finally:
        client.close()


def notificacion_a_upc(url_evidencia, descripcion):
    """Enviar notificación a UPC"""
    upc_endpoint = os.getenv("UPC_ENDPOINT", "")

    if not upc_endpoint:
        logger.info("No se configuró endpoint de UPC, omitiendo notificación")
        return False

    payload = {
        "descripcion": descripcion,
        "url_evidencia": url_evidencia,
        "fecha": datetime.now().isoformat()
    }

    try:
        respuesta = requests.post(
            upc_endpoint,
            json=payload,
            timeout=10,
            verify=False  # Desactivar verificación SSL
        )
        logger.info(f"Notificación enviada a UPC. Código: {respuesta.status_code}")
        return respuesta.status_code == 200
    except Exception as e:
        logger.error(f"Error enviando notificación a UPC: {e}")
        return False

def get_public_ip():
    """Obtener la IP pública del sistema"""
    try:
        response = requests.get("https://api.ipify.org", timeout=5)
        if response.status_code == 200:
            return response.text.strip()
        return None
    except Exception as e:
        logger.error(f"Error obteniendo IP pública: {e}")
        return None


def get_location_by_ip(ip):
    """Obtener ubicación geográfica por dirección IP"""
    if not ip:
        return {"latitud": 0, "longitud": 0}
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "success":
                return {
                    "latitud": data.get("lat"),
                    "longitud": data.get("lon")
                }
    except Exception as e:
        logger.error(f"Error obteniendo ubicación: {e}")
    return {"latitud": 0, "longitud": 0}


def extract_audio(video_path, audio_path):
    """Extraer audio de un video usando FFmpeg"""
    try:
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            audio_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception as e:
        logger.error(f"Error extrayendo audio: {e}")
        return False


def transcribe_audio(audio_path):
    """Transcribir audio usando Whisper"""
    try:
        segments, _ = whisper_model.transcribe(audio_path, language="es", beam_size=5)
        return " ".join(segment.text for segment in segments)
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        return ""


def analyze_frames(frame_paths):
    """Generar descripciones para frames usando BLIP"""
    captions = []
    for frame_path in frame_paths:
        try:
            image = Image.open(frame_path).convert("RGB")
            # Especificar max_new_tokens para evitar advertencias y controlar longitud
            result = blip_pipe(image, max_new_tokens=20)
            captions.append(result[0]['generated_text'])
        except Exception as e:
            logger.error(f"Error analizando frame {frame_path}: {e}")
            captions.append("Descripción no disponible")
    return captions


def procesar_audio(video_path, visual_json_path):
    """Procesar audio para un video y generar JSON final"""
    file_name = os.path.basename(video_path)
    logger.info(f"Procesando audio para: {file_name}")

    # Cargar análisis visual
    try:
        with open(visual_json_path, 'r', encoding='utf-8') as f:
            visual_data = json.load(f)
        logger.info("Análisis visual cargado exitosamente")
    except Exception as e:
        logger.error(f"Error cargando análisis visual: {e}")
        return

    # Extraer audio
    base_name = os.path.splitext(file_name)[0]
    audio_path = os.path.join(os.path.dirname(video_path), f"{base_name}.wav")
    if not extract_audio(video_path, audio_path):
        logger.error(f"Error extrayendo audio de: {file_name}")
        return

    # Transcribir audio
    transcription = transcribe_audio(audio_path)
    logger.info(f"Transcripción completada: {len(transcription)} caracteres")

    # Analizar frames clave
    frame_captions = []
    if "key_frames" in visual_data and visual_data["key_frames"]:
        frame_captions = analyze_frames(visual_data["key_frames"])

    # Obtener ubicación por IP pública
    public_ip = get_public_ip()
    location = get_location_by_ip(public_ip)

    # Generar JSON final
    result = {
        "descripcion": generar_descripcion_enriquecida(visual_data, transcription, frame_captions),
        "ubicacion": location,
        "ip_camara": os.getenv("CAM_IP", "192.168.100.249"),
        "url_evidencia": f"https://f000.backblazeb2.com/file/videoKr/{file_name}"
    }

    # Guardar resultado
    output_path = os.path.join(os.path.dirname(visual_json_path), f"{base_name}_final.json")
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info(f"Análisis completo guardado en: {output_path}")

    # Guardar en MongoDB Atlas
    guardar_en_mongodb(result)

    # Enviar notificación a UPC
    notificacion_a_upc(result["url_evidencia"], result["descripcion"])

    # Limpiar archivos temporales
    try:
        os.remove(audio_path)
        for frame_path in visual_data.get("key_frames", []):
            os.remove(frame_path)
    except Exception as e:
        logger.error(f"Error eliminando archivos temporales: {e}")