import os
import time
import json
import requests
import subprocess
import logging
import ssl
import certifi
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


def guardar_json_mongodb(db_name, collection_name, data):
    """Guarda un documento JSON en MongoDB local"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        result = collection.insert_one(data)
        logger.info(f"JSON guardado en MongoDB: {collection_name} - ID: {result.inserted_id}")
        return True
    except Exception as e:
        logger.error(f"Error guardando en MongoDB: {e}")
        return False
    finally:
        client.close()


def notificacion_a_upc(url_evidencia, descripcion):
    """Envía notificación a UPC usando el endpoint FastAPI"""
    try:
        # Construir evidencia básica
        evidencia = {
            "descripcion": descripcion,
            "url_evidencia": url_evidencia,
            "fecha": datetime.now().isoformat()
        }

        # Llamar al endpoint local de FastAPI
        local_upc_endpoint = "http://localhost:8000/enviar-evidencia-upc"
        response = requests.post(local_upc_endpoint, json=evidencia, timeout=5)

        if response.status_code == 200:
            logger.info("Notificación enviada a UPC a través de FastAPI")
            return True
        else:
            logger.error(f"Error enviando a UPC: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Excepción al enviar a UPC: {e}")
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


def procesar_audio(video_path, visual_data, username, video_filename, b2_path):
    """Procesa audio y genera JSON final"""
    # Análisis de frames siempre se ejecuta
    frame_captions = []
    if visual_data.get("key_frames"):
        frame_captions = analyze_frames(visual_data["key_frames"])

    # Procesar audio si es posible (no bloqueante)
    transcription = ""
    try:
        audio_path = f"temp_{video_filename}.wav"
        if extract_audio(video_path, audio_path):
            transcription = transcribe_audio(audio_path) or ""
            os.remove(audio_path)
    except Exception as e:
        logger.error(f"Error procesando audio: {e}")

    # Construir JSON final con URL público de Backblaze
    base_url = os.getenv("B2_PUBLIC_BASE_URL", "https://f005.backblazeb2.com/file/evidenciaskunturmovilidad/")
    public_url = f"{base_url}{b2_path}"

    # Construir objeto evidencia
    evidencia = {
        "descripcion": generar_descripcion_enriquecida(visual_data, transcription, frame_captions),
        "ubicacion": get_location_by_ip(get_public_ip()),
        "ip_camara": os.getenv("CAM_IP", ""),
        "usuario": username,
        "url_evidencia": public_url,
        "fecha": datetime.now().isoformat(),
        "b2_path": b2_path,
        "estado": "nuevo"  # Estado inicial: nuevo
    }

    # Guardar en MongoDB local (colección Evidencias)
    guardar_json_mongodb("Kuntur", "Evidencias", evidencia)

    # Enviar notificación a UPC
    notificacion_a_upc(public_url, evidencia["descripcion"])

    # Limpiar archivos temporales
    try:
        for frame_path in visual_data.get("key_frames", []):
            os.remove(frame_path)
    except Exception as e:
        logger.error(f"Error eliminando archivos temporales: {e}")