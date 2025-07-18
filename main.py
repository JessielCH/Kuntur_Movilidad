from fastapi import FastAPI, HTTPException, Request, Form, Depends, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import json
from datetime import datetime
from utils.db_utils import get_db, User, get_user_data, verify_user, create_user, init_db
import logging
import requests
from typing import Dict, Any

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# Montar carpetas estáticas y de templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Configuración MongoDB
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "kuntur_db")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "alertas")

# Conectar a MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    logger.info("Conexión a MongoDB establecida")
except Exception as e:
    logger.error(f"Error conectando a MongoDB: {e}")
    db = None
    collection = None


# Función auxiliar para guardar en MongoDB (reutilizable)
def guardar_json_mongodb(db_name: str, collection_name: str, data: Dict[str, Any]):
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client[db_name]
        collection = db[collection_name]
        result = collection.insert_one(data)
        return {"inserted_id": str(result.inserted_id)}
    except Exception as e:
        logger.error(f"Error guardando en MongoDB: {e}")
        return None
    finally:
        client.close()


# Endpoints para la aplicación web
@app.get("/", response_class=HTMLResponse)
async def read_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/", response_class=HTMLResponse)
async def login(request: Request, usuario: str = Form(...), password: str = Form(...)):
    if verify_user(usuario, password):
        return RedirectResponse(url=f"/camara?usuario={usuario}", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Credenciales inválidas"})


@app.get("/registro", response_class=HTMLResponse)
async def read_registro(request: Request):
    return templates.TemplateResponse("registro.html", {"request": request})


@app.post("/registro", response_class=HTMLResponse)
async def registro(request: Request,
                   usuario: str = Form(...),
                   password: str = Form(...),
                   confirm_password: str = Form(...),
                   unidad: str = Form(...),
                   chofer: str = Form(...),
                   ip_camara: str = Form(...)):
    if password != confirm_password:
        return templates.TemplateResponse("registro.html",
                                          {"request": request, "error": "Las contraseñas no coinciden"})

    try:
        create_user(usuario, password, unidad, chofer, ip_camara)
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        return templates.TemplateResponse("registro.html", {"request": request, "error": str(e)})


@app.get("/camara", response_class=HTMLResponse)
async def camara(request: Request, usuario: str):
    user_data = get_user_data(usuario)
    if not user_data:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse("camara.html", {
        "request": request,
        "usuario": usuario,
        "ip_camara": user_data['ip_camara']
    })


# Endpoint para enviar evidencias a UPC
@app.post("/enviar-evidencia-upc")
async def enviar_evidencia_upc(evidencia: dict):
    """
    Envía una evidencia al sistema de la UPC
    Ejemplo de JSON:
    {
        "descripcion": "Persona con arma de fuego...",
        "url_evidencia": "https://.../video.mp4",
        "ubicacion": {"lat": -12.123, "lng": -77.456},
        "ip_camara": "192.168.1.100",
        "usuario": "user123",
        "fecha": "2024-07-18T12:34:56Z"
    }
    """
    try:
        # Validar campos requeridos
        required_fields = ["descripcion", "url_evidencia", "usuario", "fecha"]
        if not all(field in evidencia for field in required_fields):
            raise HTTPException(
                status_code=400,
                detail=f"Faltan campos requeridos: {required_fields}"
            )

        # Enviar a UPC
        upc_endpoint = os.getenv("UPC_ENDPOINT", "https://api.upc.edu.pe/alertas")
        response = requests.post(upc_endpoint, json=evidencia, timeout=10)

        if response.status_code == 200:
            return {"status": "success", "message": "Evidencia enviada a UPC"}
        else:
            logger.error(f"Error UPC: {response.status_code} - {response.text}")
            return {"status": "error", "message": "Error en servidor UPC"}

    except Exception as e:
        logger.error(f"Error enviando a UPC: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint para recibir resoluciones de Justicia
@app.post("/resoluciones")
async def recibir_resolucion(resolucion: dict):
    """
    Recibe una resolución del sistema de Justicia
    Ejemplo de JSON:
    {
        "id_evidencia": "665f1a2d8f4bae1a3d4e5f6a",
        "resolucion": "Caso cerrado",
        "fecha_resolucion": "2024-07-20",
        "detalles": "Sospechoso capturado",
        "codigo_caso": "C-2024-0789"
    }
    """
    try:
        # Validar campos requeridos
        required_fields = ["id_evidencia", "resolucion", "fecha_resolucion"]
        if not all(field in resolucion for field in required_fields):
            raise HTTPException(
                status_code=400,
                detail=f"Faltan campos requeridos: {required_fields}"
            )

        # Agregar timestamp de recepción
        resolucion["fecha_recepcion"] = datetime.now().isoformat()

        # Guardar en MongoDB en la colección Resoluciones
        guardar_json_mongodb("Kuntur", "Resoluciones", resolucion)
        return {"status": "success", "message": "Resolución almacenada"}

    except Exception as e:
        logger.error(f"Error procesando resolución: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint para recibir videos de la cámara
@app.post("/upload-video")
async def upload_video(usuario: str, video: UploadFile = File(...)):
    """Endpoint para recibir videos de la cámara IP"""
    try:
        # Crear carpeta para el usuario si no existe
        user_folder = os.path.join("data", "videos", usuario)
        os.makedirs(user_folder, exist_ok=True)

        # Generar nombre de archivo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{usuario}_{timestamp}.mp4"
        file_path = os.path.join(user_folder, filename)

        # Guardar el video
        with open(file_path, "wb") as f:
            f.write(await video.read())

        return {"mensaje": "Video recibido", "ruta": file_path}
    except Exception as e:
        logger.error(f"Error subiendo video: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el video")


# Endpoint para listar evidencias (para pruebas)
@app.get("/evidencias")
async def listar_evidencias():
    """Obtener todas las evidencias (para pruebas)"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client["Kuntur"]
        collection = db["Evidencias"]
        evidencias = list(collection.find({}, {"_id": 0}))
        return {"evidencias": evidencias}
    except Exception as e:
        return {"error": str(e)}


# Endpoint para listar resoluciones (para pruebas)
@app.get("/resoluciones")
async def listar_resoluciones():
    """Obtener todas las resoluciones (para pruebas)"""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client["Kuntur"]
        collection = db["Resoluciones"]
        resoluciones = list(collection.find({}, {"_id": 0}))
        return {"resoluciones": resoluciones}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn

    init_db()  # Asegurar que la base de datos SQLite esté inicializada
    uvicorn.run(app, host="0.0.0.0", port=8000)