import os
import cv2
import json
import numpy as np
import pandas as pd
import torch
from datetime import datetime
from collections import defaultdict
import logging

# Configura logging
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

# Importar Ultralytics después de configurar el entorno
from ultralytics import YOLO

# Importar utilidades locales
from .distance_utils import calcular_distancia_real
from .alert_system import SistemaAlertas
from .llm_utils import generar_justificacion

# Configuración (usar variables de entorno)
MODEL_PERSONAS = os.getenv("MODEL_PERSONAS", "modelos/yolov8n.pt")
MODEL_ARMAS = os.getenv("MODEL_ARMAS", "modelos/weapon_yolov8n.pt")

# Parámetros de detección
DISTANCIA_UMBRAL = float(os.getenv("DISTANCIA_UMBRAL", 1.5))
MIN_TIEMPO_ACOSO = int(os.getenv("MIN_TIEMPO_ACOSO", 10))
MIN_ACERCAMIENTO = float(os.getenv("MIN_ACERCAMIENTO", 0.2))
MAX_AREA_RATIO = float(os.getenv("MAX_AREA_RATIO", 0.1))
MARGEN_ARMAS = int(os.getenv("MARGEN_ARMAS", 30))

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
    """Carga el modelo de forma segura evitando problemas de weights_only"""
    # Si es el modelo de armas, asegurarse de que existe
    if "weapon" in ruta_modelo:
        descargar_modelo_armas(ruta_modelo)

    try:
        # Cargar directamente con Ultralytics
        return YOLO(ruta_modelo)
    except Exception as e:
        logger.error(f"Error cargando modelo ({e}), intentando carga alternativa...")
        try:
            # Cargar con torch directamente
            model = torch.hub.load('ultralytics/yolov5', 'custom', path=ruta_modelo)
            return model
        except Exception as e2:
            logger.error(f"Error en carga alternativa: {str(e2)}")
            raise RuntimeError(f"No se pudo cargar el modelo: {ruta_modelo}")

def calcular_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    total_area = areaA + areaB - inter
    return inter / total_area if total_area > 0 else 0

def arma_cerca_de_persona(arma_box, cajas_personas, margen):
    """Determina si un arma está cerca de alguna persona"""
    ax1, ay1, ax2, ay2 = arma_box
    arma_centro = ((ax1 + ax2) // 2, (ay1 + ay2) // 2)

    for tid, p_box in cajas_personas.items():
        px1, py1, px2, py2 = p_box
        # Expandir caja de persona con margen
        px1_exp = px1 - margen
        py1_exp = py1 - margen
        px2_exp = px2 + margen
        py2_exp = py2 + margen

        # Verificar si el centro del arma está dentro del área expandida
        if (px1_exp <= arma_centro[0] <= px2_exp and
                py1_exp <= arma_centro[1] <= py2_exp):
            return True

        # Verificar si hay superposición
        if calcular_iou(arma_box, (px1_exp, py1_exp, px2_exp, py2_exp)) > 0.05:
            return True

    return False

def procesar_video(video_path):
    # Inicializar modelos con carga segura
    try:
        yolo_personas = cargar_modelo_seguro(MODEL_PERSONAS)
        yolo_armas = cargar_modelo_seguro(MODEL_ARMAS)
    except Exception as e:
        logger.error(f"Error crítico cargando modelos: {str(e)}")
        return {"error": str(e)}, ""

    sistema = SistemaAlertas()

    # Resultados
    resultados = {
        "video": os.path.basename(video_path),
        "fecha_procesamiento": datetime.now().isoformat(),
        "alertas": [],
        "tipo_evento": "",
        "confianza": 0,
        "frame_detectado": 0,
        "estadisticas": {
            "personas": 0,
            "armas": 0,
            "interacciones": 0
        }
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

    historial = defaultdict(list)
    timestamps = defaultdict(list)
    frame_count = 0
    res_pers = None
    res_armas = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        tiempo_actual = frame_count / fps if fps > 0 else frame_count

        # Detección de personas
        if frame_count % 3 == 0 or res_pers is None:
            try:
                if hasattr(yolo_personas, 'track'):
                    res_pers = yolo_personas.track(frame, persist=True, classes=[0], imgsz=320, conf=0.3, verbose=False)
                    res_pers = res_pers[0] if res_pers else None
                else:
                    # Fallback para YOLOv5
                    results = yolo_personas(frame)
                    res_pers = results.pandas().xyxy[0] if results else None
            except Exception as e:
                logger.error(f"Error en detección de personas: {str(e)}")
                res_pers = None

        cajas = {}
        if res_pers is not None:
            try:
                # Manejar diferentes formatos de resultados
                if hasattr(res_pers, 'boxes'):  # Formato Ultralytics
                    for box in res_pers.boxes:
                        tid = int(box.id.item()) if box.id is not None else None
                        if tid is not None:
                            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                            cajas[tid] = (x1, y1, x2, y2)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(frame, f"ID:{tid}", (x1, y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                elif isinstance(res_pers, pd.DataFrame):  # Formato YOLOv5
                    for _, row in res_pers.iterrows():
                        if row['class'] == 0 and row['confidence'] > 0.3:  # Personas
                            x1, y1, x2, y2 = int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax'])
                            tid = row.get('id', hash((x1, y1, x2, y2)))  # ID de emergencia
                            cajas[tid] = (x1, y1, x2, y2)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(frame, f"ID:{tid}", (x1, y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            except Exception as e:
                logger.error(f"Error procesando cajas personas: {str(e)}")

        # Detección de armas - SOLO SI HAY PERSONAS
        armas = []
        if cajas:  # Solo buscar armas si hay personas detectadas
            if frame_count % 6 == 0 or res_armas is None:
                try:
                    if hasattr(yolo_armas, 'track'):
                        res_armas = yolo_armas.track(frame, persist=True, imgsz=640, conf=0.5, verbose=False)
                        res_armas = res_armas[0] if res_armas else None
                    else:
                        # Fallback para YOLOv5
                        results = yolo_armas(frame)
                        res_armas = results.pandas().xyxy[0] if results else None
                except Exception as e:
                    logger.error(f"Error en detección de armas: {str(e)}")
                    res_armas = None

            if res_armas is not None:
                try:
                    # Manejar diferentes formatos de resultados
                    if hasattr(res_armas, 'boxes'):  # Formato Ultralytics
                        for box in res_armas.boxes:
                            conf = box.conf.item()
                            if conf > 0.5:
                                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                                area = (x2 - x1) * (y2 - y1)

                                # Filtrar armas demasiado grandes
                                if area / (frame.shape[0] * frame.shape[1]) > MAX_AREA_RATIO:
                                    continue

                                # Solo considerar armas cerca de personas
                                if not arma_cerca_de_persona((x1, y1, x2, y2), cajas, MARGEN_ARMAS):
                                    continue

                                armas.append((x1, y1, x2, y2, conf))
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                                cv2.putText(frame, f"ARMA {conf:.2f}", (x1, y1 - 10),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                    elif isinstance(res_armas, pd.DataFrame):  # Formato YOLOv5
                        for _, row in res_armas.iterrows():
                            if row['confidence'] > 0.5:  # Armas
                                x1, y1, x2, y2 = int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax'])
                                area = (x2 - x1) * (y2 - y1)

                                # Filtrar armas demasiado grandes
                                if area / (frame.shape[0] * frame.shape[1]) > MAX_AREA_RATIO:
                                    continue

                                # Solo considerar armas cerca de personas
                                if not arma_cerca_de_persona((x1, y1, x2, y2), cajas, MARGEN_ARMAS):
                                    continue

                                armas.append((x1, y1, x2, y2, row['confidence']))
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                                cv2.putText(frame, f"ARMA {row['confidence']:.2f}", (x1, y1 - 10),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                except Exception as e:
                    logger.error(f"Error procesando cajas armas: {str(e)}")

        # Detección de interacciones
        posibles_acosadores = []
        ids = list(cajas.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                try:
                    id1, id2 = ids[i], ids[j]
                    b1, b2 = cajas[id1], cajas[id2]
                    d = calcular_distancia_real(b1, b2, frame.shape)

                    if d < DISTANCIA_UMBRAL:
                        par = tuple(sorted((id1, id2)))
                        historial[par].append(d)
                        timestamps[par].append(tiempo_actual)

                        # Mantener solo últimos 30 segundos
                        historial[par] = [h for idx, h in enumerate(historial[par])
                                          if (tiempo_actual - timestamps[par][idx]) <= 30]
                        timestamps[par] = [t for t in timestamps[par]
                                           if (tiempo_actual - t) <= 30]

                        if len(historial[par]) > 2 and \
                                (historial[par][0] - historial[par][-1]) > MIN_ACERCAMIENTO and \
                                (timestamps[par][-1] - timestamps[par][0]) > MIN_TIEMPO_ACOSO:
                            posibles_acosadores.append((id1, id2, d))

                        cx1, cy1 = (b1[0] + b1[2]) // 2, (b1[1] + b1[3]) // 2
                        cx2, cy2 = (b2[0] + b2[2]) // 2, (b2[1] + b2[3]) // 2
                        cv2.line(frame, (cx1, cy1), (cx2, cy2), (0, 0, 255), 2)
                        cv2.putText(frame, f"{d:.2f}m", ((cx1 + cx2) // 2, (cy1 + cy2) // 2),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                except Exception as e:
                    logger.error(f"Error calculando interacción: {str(e)}")

        # Manejo de alertas
        if armas:
            sistema.activar("ARMA_DETECTADA")
            resultados["alertas"].append({
                "tiempo": tiempo_actual,
                "tipo": "ARMA_DETECTADA",
                "descripcion": f"Detectada arma con confianza {armas[0][4]:.2f} cerca de persona"
            })

        elif posibles_acosadores and sistema.registrar(len(posibles_acosadores)):
            sistema.activar("POSIBLE_ACOSO")
            descripcion = f"{len(posibles_acosadores)} interacciones sospechosas"
            resultados["alertas"].append({
                "tiempo": tiempo_actual,
                "tipo": "POSIBLE_ACOSO",
                "descripcion": descripcion,
                "justificacion": generar_justificacion(descripcion)
            })

        # Guardar frame procesado
        out.write(frame)

    # Finalizar
    cap.release()
    out.release()

    # Estadísticas finales
    resultados["estadisticas"] = {
        "personas": len(cajas),
        "armas": len(armas),
        "interacciones": len(posibles_acosadores)
    }

    # Determinar evento principal
    if resultados["alertas"]:
        ultima_alerta = resultados["alertas"][-1]
        resultados["tipo_evento"] = ultima_alerta["tipo"]
        resultados["confianza"] = 0.8  # Valor por defecto
        resultados["frame_detectado"] = int(ultima_alerta["tiempo"] * fps)

    return resultados, video_salida