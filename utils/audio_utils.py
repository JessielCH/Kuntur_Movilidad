import os
import time
import json
import requests
import subprocess
import logging
from faster_whisper import WhisperModel
from utils.llm_utils import generar_resumen, generar_descripcion_enriquecida

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar modelo Whisper
model = WhisperModel("small", device="cpu", compute_type="int8")

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
        return {"ciudad": "Desconocida", "pais": "Desconocido", "latitud": 0, "longitud": 0}
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "success":
                return {
                    "ciudad": data.get("city", "Desconocida"),
                    "pais": data.get("country", "Desconocido"),
                    "latitud": data.get("lat"),
                    "longitud": data.get("lon")
                }
    except Exception as e:
        logger.error(f"Error obteniendo ubicación: {e}")
    return {"ciudad": "Desconocida", "pais": "Desconocido", "latitud": 0, "longitud": 0}

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
        segments, _ = model.transcribe(audio_path, language="es", beam_size=5)
        return " ".join(segment.text for segment in segments)
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        return ""

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
    summary = generar_resumen(transcription) if transcription and len(transcription) > 10 else "Sin contenido para resumir"
    logger.info(f"Transcripción completada: {len(transcription)} caracteres")

    # Obtener ubicación por IP pública
    public_ip = get_public_ip()
    location = get_location_by_ip(public_ip)
    logger.info(f"Ubicación detectada: {location['ciudad']}, {location['pais']}")

    # Generar JSON final
    result = {
        "descripcion_delito": generar_descripcion_enriquecida(visual_data, transcription),
        "url_evidencia": f"https://f000.backblazeb2.com/file/videoKr/{file_name}",
        "ip_camara": os.getenv("CAM_IP", "192.168.100.249"),
        "ubicacion_ip": location,
        "analisis_visual": {
            "tipo_evento": visual_data.get("tipo_evento", ""),
            "confianza": visual_data.get("confianza", 0),
            "frame_detectado": visual_data.get("frame_detectado", 0)
        },
        "resumen_audio": summary  # Solo el resumen, no la transcripción completa
    }

    # Guardar resultado
    output_path = os.path.join(os.path.dirname(visual_json_path), f"{base_name}_final.json")
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info(f"Análisis completo guardado en: {output_path}")

    # Limpiar archivos temporales
    try:
        os.remove(audio_path)
        os.remove(video_path)
    except Exception as e:
        logger.error(f"Error eliminando archivos temporales: {e}")