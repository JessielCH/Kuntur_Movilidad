from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
import logging
import os

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
MODEL_LLM = "llama3-8b-8192"


def generar_justificacion(descripcion):
    prompt = ChatPromptTemplate.from_template(
        "Eres un experto en seguridad. Genera una justificación técnica concisa "
        "(máximo 2 oraciones) en español para esta alerta:\n"
        "Alerta: {alerta}\n\n"
        "Justificación:"
    )

    try:
        llm = ChatGroq(temperature=0.7, model_name=MODEL_LLM, api_key=GROQ_API_KEY)
        chain = prompt | llm
        return chain.invoke({"alerta": descripcion}).content
    except Exception as e:
        logger.error(f"Error generando justificación: {e}")
        return "Justificación no disponible"


def generar_resumen(texto):
    """Generar resumen del texto usando LLM"""
    if not texto or len(texto.strip()) < 10:
        return "Sin contenido para resumir"

    prompt = ChatPromptTemplate.from_template(
        "Eres un experto en seguridad. Genera un resumen conciso (1-2 frases) en español "
        "del siguiente texto relacionado con un incidente de seguridad:\n"
        "Texto: {texto}\n\n"
        "Resumen:"
    )

    try:
        llm = ChatGroq(temperature=0.5, model_name=MODEL_LLM, api_key=GROQ_API_KEY)
        chain = prompt | llm
        return chain.invoke({"texto": texto}).content
    except Exception as e:
        logger.error(f"Error generando resumen: {e}")
        return "Resumen no disponible"


def generar_descripcion_enriquecida(analisis_visual, transcripcion_audio):
    """Generar descripción enriquecida combinando análisis visual y auditivo"""
    # Extraer información visual
    eventos = []
    if "alertas" in analisis_visual:
        for alerta in analisis_visual["alertas"]:
            eventos.append(f"{alerta['tipo']} (confianza: {alerta.get('confianza', 0):.2f})")

    info_visual = ", ".join(eventos) if eventos else "Sin eventos visuales detectados"

    # Limitar tamaño de transcripción
    transcripcion_limitada = transcripcion_audio[:1000] if transcripcion_audio else "Sin audio"

    # Crear prompt para LLM
    prompt = ChatPromptTemplate.from_template(
        "Eres un analista de seguridad experto en temas de asaltos y acosos en transporte publico. Si detectas dentro del audio palabras como Telefono,Catera,Celular o parecidos hablamos de un asalto"
        "si detectas palabras como hola guapa hermosa y asi hablamos de acoso. Combina la siguiente información para crear "
        "una descripción coherente de un posible incidente de seguridad:\n\n"
        "Análisis visual: {info_visual}\n"
        "Transcripción de audio: {transcripcion}\n\n"
        "Genera una descripción de 2-3 oraciones en español que integre ambas fuentes de información:"
    )

    try:
        llm = ChatGroq(temperature=0.7, model_name=MODEL_LLM, api_key=GROQ_API_KEY)
        chain = prompt | llm
        return chain.invoke({
            "info_visual": info_visual,
            "transcripcion": transcripcion_limitada
        }).content
    except Exception as e:
        logger.error(f"Error generando descripción enriquecida: {e}")
        return "Descripción no disponible"