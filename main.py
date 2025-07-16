import os
import uuid
import time
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de carpetas
CARPETA_VIDEOS = "./data/videos"
os.makedirs(CARPETA_VIDEOS, exist_ok=True)


@app.post("/upload-video/")
async def upload_video(file: UploadFile = File(...)):
    # Aceptar múltiples tipos de video
    valid_types = [
        "video/webm",
        "video/mp4",
        "video/quicktime",  # Para mov
        "video/x-msvideo",  # Para avi
        "application/octet-stream"  # Tipo genérico
    ]

    if file.content_type not in valid_types:
        # Verificar por extensión si el tipo MIME falla
        filename = file.filename.lower()
        if not any(filename.endswith(ext) for ext in ['.webm', '.mp4', '.mov', '.avi']):
            raise HTTPException(400, "Tipo de archivo no soportado. Formatos aceptados: .webm, .mp4, .mov, .avi")

    # Generar nombre único
    file_ext = os.path.splitext(file.filename)[1] or ".webm"
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(CARPETA_VIDEOS, unique_filename)

    try:
        start_time = time.time()

        # Guardar el archivo
        with open(file_path, "wb") as f:
            while content := await file.read(1024 * 1024):  # Leer en chunks de 1MB
                f.write(content)

        file_size = os.path.getsize(file_path)
        elapsed = time.time() - start_time

        return {
            "message": f"Video guardado ({file_size / 1024:.1f} KB en {elapsed:.2f}s)",
            "file_name": unique_filename,
            "file_size": file_size
        }

    except Exception as e:
        # Intentar eliminar archivo incompleto
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(500, f"Error al guardar el video: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)