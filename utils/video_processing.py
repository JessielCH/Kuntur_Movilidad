import logging
import os
from datetime import datetime

import cv2
import torch
from ultralytics import YOLO

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurar entorno antes de importar Ultralytics
os.environ['ULTRALYTICS_AUTOUPDATE'] = 'disabled'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# ===== WORKAROUND PARA ULTRALYTICS 8.2.0 =====
import ultralytics.utils.loss as loss_module


class DFLoss:
    def __init__(self, *args, **kwargs):
        pass


if not hasattr(loss_module, 'DFLoss'):
    loss_module.DFLoss = DFLoss
# ===== FIN WORKAROUND =====

# Configuración (usar variables de entorno)
MODEL_ARMAS = os.getenv("MODEL_ARMAS", "modelos/weapon_yolov8n.pt")
MAX_AREA_RATIO = float(os.getenv("MAX_AREA_RATIO", 0.1))
MARGEN_ARMAS = int(os.getenv("MARGEN_ARMAS", 30))

# Definir carpeta de frames
CARPETA_FRAMES = os.path.join("data", "frames")


def descargar_modelo_armas(ruta):
    """Descarga el modelo de armas si no existe"""
    if os.path.exists(ruta):
        return

    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    logger.info(f"Descargando modelo de armas en: {ruta}")

    try:
        import gdown
        gdown.download(
            "https://drive.google.com/uc?id=1ZgqjONv3q43H9eBd5cG6JNkYd6tOjf1D",
            ruta, quiet=False
        )
        logger.info("Modelo descargado desde Google Drive")
    except Exception as e:
        logger.error(f"Error al descargar modelo: {str(e)}")
        raise


def cargar_modelo_seguro(ruta_modelo):
    """Carga el modelo de forma segura"""
    # Asegurarse de que existe el modelo
    if "weapon" in ruta_modelo:
        descargar_modelo_armas(ruta_modelo)

    try:
        return YOLO(ruta_modelo)
    except Exception as e:
        logger.error(f"Error cargando modelo: {str(e)}")
        raise RuntimeError(f"No se pudo cargar el modelo: {ruta_modelo}")


def procesar_video(video_path):
    # Inicializar modelo de armas
    try:
        yolo_armas = cargar_modelo_seguro(MODEL_ARMAS)
    except Exception as e:
        logger.error(f"Error crítico cargando modelo: {str(e)}")
        return {"error": str(e)}, ""

    # Resultados
    resultados = {
        "video": os.path.basename(video_path),
        "fecha_procesamiento": datetime.now().isoformat(),
        "alertas": [],
        "key_frames": []  # Frames clave para análisis
    }

    # Preparar video de salida
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Error abriendo video: {video_path}")
        return resultados, ""

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    video_salida = f"procesado_{os.path.basename(video_path)}"
    out = cv2.VideoWriter(
        video_salida,
        cv2.VideoWriter_fourcc(*'mp4v'),
        fps,
        (width, height)
    )

    frame_count = 0
    res_armas = None
    arma_detectada = False
    key_frames = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        tiempo_actual = frame_count / fps if fps > 0 else frame_count

        # Detección de armas
        if frame_count % 6 == 0 or res_armas is None:
            try:
                res_armas = yolo_armas.track(frame, persist=True, imgsz=640, conf=0.5, verbose=False)
                res_armas = res_armas[0] if res_armas else None
            except Exception as e:
                logger.error(f"Error en detección de armas: {str(e)}")
                res_armas = None

        armas = []
        if res_armas is not None:
            try:
                if hasattr(res_armas, 'boxes'):
                    for box in res_armas.boxes:
                        conf = box.conf.item()
                        if conf > 0.5:
                            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                            area = (x2 - x1) * (y2 - y1)

                            # Filtrar armas demasiado grandes
                            if area / (frame.shape[0] * frame.shape[1]) > MAX_AREA_RATIO:
                                continue

                            armas.append((x1, y1, x2, y2, conf))
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                            cv2.putText(frame, f"ARMA {conf:.2f}", (x1, y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            except Exception as e:
                logger.error(f"Error procesando cajas armas: {str(e)}")

        # Manejo de alertas
        if armas:
            arma_detectada = True
            resultados["alertas"].append({
                "tiempo": tiempo_actual,
                "tipo": "armaDetectada",
                "confianza": armas[0][4]
            })

            # Guardar frame clave (máximo 3)
            if len(key_frames) < 3:
                os.makedirs(CARPETA_FRAMES, exist_ok=True)
                frame_name = f"frame_{frame_count}.jpg"
                frame_path = os.path.join(CARPETA_FRAMES, frame_name)
                cv2.imwrite(frame_path, frame)
                key_frames.append(frame_path)
                resultados["key_frames"] = key_frames

        # Guardar frame procesado
        out.write(frame)

    # Finalizar
    cap.release()
    out.release()

    return resultados, video_salida