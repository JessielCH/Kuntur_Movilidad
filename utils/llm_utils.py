from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
import logging
import os
import re

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
MODEL_LLM = "llama3-8b-8192"

PALABRAS_CLAVE = ["cartera", "celular", "dame", "quieto", "disparo", "arma", "matar",
                  "muerte", "ayuda", "robo", "asalto", "pistola", "revólver", "cuchillo",
                  "dispara", "asesino", "socorro", "ladrón", "delincuente", "hurto",
                  "móvil", "telefono", "bolso", "cartera", "billetera", "dinero", "anillo"]


def contiene_palabras_clave(texto):
    """Revisar si el texto contiene palabras clave de peligro con similitud"""
    if not texto:
        return False

    texto = texto.lower()
    for palabra in PALABRAS_CLAVE:
        # Buscar palabras similares (ej: "celular", "celulares", "cel")
        if re.search(rf"\b{palabra[:3]}", texto):
            return True
    return False


def generar_descripcion_enriquecida(analisis_visual, transcripcion_audio, frame_captions):
    """Generar descripción enriquecida concisa (50-100 palabras)"""
    # Información de alertas
    alertas_info = ""
    if "alertas" in analisis_visual and analisis_visual["alertas"]:
        alerta = analisis_visual["alertas"][0]
        alertas_info = f"Alerta: {alerta['tipo']} (conf: {alerta['confianza']:.2f})"

    # Información de audio
    audio_info = ""
    if contiene_palabras_clave(transcripcion_audio):
        palabras_detectadas = [p for p in PALABRAS_CLAVE if re.search(rf"\b{p[:3]}", transcripcion_audio.lower())]
        audio_info = f"Palabras clave: {', '.join(palabras_detectadas[:3])}"
    elif transcripcion_audio:
        audio_info = "Sin palabras clave relevantes"

    # Información de frames
    frames_info = " | ".join(frame_captions) if frame_captions else "Sin capturas"

    # Crear prompt para LLM
    prompt = ChatPromptTemplate.from_template(
        "Eres un experto en seguridad en transporte publico. En 50-100 palabras, genera una descripción concisa de un asalto. "
        "Usa solo la información relevante. Información:\n"
        "Visual: {alertas_info}\n"
        "Audio: {audio_info}\n"
        "Frames: {frames_info}\n"
        "Descripción:"
    )

    try:
        llm = ChatGroq(temperature=0.7, model_name=MODEL_LLM, api_key=GROQ_API_KEY)
        chain = prompt | llm
        descripcion = chain.invoke({
            "alertas_info": alertas_info,
            "audio_info": audio_info,
            "frames_info": frames_info
        }).content

        return descripcion
    except Exception as e:
        logger.error(f"Error generando descripción enriquecida: {e}")
        return "Descripción no disponible"