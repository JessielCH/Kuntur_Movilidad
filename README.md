# Kuntur - Sistema de Seguridad para Transporte Público 🦅🚌  

**Kuntur** es un sistema avanzado de seguridad para el transporte público que utiliza inteligencia artificial para detectar **armas** y **situaciones de riesgo** en tiempo real. El sistema analiza video desde cámaras IP, procesa audio ambiental y genera alertas automáticas para las autoridades.

---

## ✨ Características Clave  

- 🔍 **Detección de armas en tiempo real** con YOLOv8  
- 🎙️ **Análisis de audio** con Whisper para detectar palabras clave de peligro  
- 📹 **Grabación segmentada automática** y subida a Backblaze B2  
- 🚨 **Botón de pánico** integrado para alertas manuales  
- 📊 **Dashboard web** con geolocalización en tiempo real  
- 📚 **Base de datos estructurada** para evidencias y resoluciones  
- 🤖 **Descripciones enriquecidas** con Groq + LLaMA 3  

---

## 🏗️ Arquitectura del Sistema  

```text
Cámara IP ──▶ Servidor FastAPI ──▶ Procesamiento IA (YOLOv8 + Whisper + BLIP + Llama3)
                                ├──▶ Backblaze (Evidencia)
                                ├──▶ MongoDB (Alertas)
                                └──▶ Dashboard Web
```

---

## 📋 Requisitos Previos  

- Python 3.9+
- MongoDB (local o Atlas)
- Cuenta en Backblaze B2
- Clave API de Groq
- Cámara IP compatible (`http://[IP]:8080/video`)

---

## ⚙️ Instalación  

1. **Clona el repositorio:**  
```bash
git clone https://github.com/JessielCH/Kuntur_Movilidad.git
cd Kuntur_Movilidad
```

2. **Crea y activa un entorno virtual:**  
```bash
# Linux/MacOS
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

3. **Instala las dependencias:**  
```bash
pip install -r requirements.txt
```

4. **Configura las variables de entorno (.env):**  
```ini
# Backblaze
B2_KEY_ID=tu_key_id
B2_APP_KEY=tu_app_key
B2_BUCKET_ID=tu_bucket_id
B2_PUBLIC_BASE_URL=https://f005.backblazeb2.com/file/tu-bucket/

# MongoDB
MONGO_URI=mongodb://localhost:27017/
MONGO_DB=kuntur_db
MONGO_COLLECTION=alertas

# Groq
GROQ_API_KEY=tu_api_key_de_groq

# Otros
CAM_IP=192.168.1.100
```

5. **Inicializa la base de datos:**  
```bash
python -c "from db_utils import init_db; init_db()"
```

---

## 🚀 Uso  

**Iniciar servidor principal (API + interfaz web):**  
```bash
uvicorn main:app --reload --port 8000
```

**Iniciar procesador de videos:**  
```bash
python local_processor.py
```

**Accede al sistema:**  
[http://localhost:8000](http://localhost:8000)

---

## 📂 Estructura de Archivos  

```text
kuntur/
├── data/
│   ├── videos/             # Videos sin procesar
│   ├── procesados/         # Videos analizados
│   └── frames/             # Frames clave con armas
├── static/
│   └── img/                # Recursos gráficos
├── templates/
│   ├── camara.html         # Interfaz de cámara
│   ├── login.html          # Inicio de sesión
│   └── registro.html       # Registro de usuario
├── utils/
│   ├── audio_utils.py
│   ├── backblaze_utils.py
│   ├── db_utils.py
│   ├── llm_utils.py
│   └── video_processing.py
├── local_processor.py      # Módulo de análisis local
├── main.py                 # Servidor FastAPI
├── db_utils.py             # DB helper
├── requirements.txt        # Requisitos Python
└── README.md               # Este archivo
```

---

## 🛠️ Tecnologías Utilizadas  

**Inteligencia Artificial:**  
- YOLOv8 – Detección de armas  
- Whisper – Análisis de audio  
- BLIP – Captioning de imágenes  
- LLaMA3 (Groq) – Enriquecimiento de descripciones  

**Backend:**  
- FastAPI – API Web  
- MongoDB – Evidencias  
- SQLite – Usuarios  
- Backblaze B2 – Almacenamiento externo  

**Frontend:**  
- Jinja2 – Plantillas HTML  
- Bootstrap 5 – Diseño responsive  
- Leaflet – Mapas interactivos  

---

## 🤝 Contribución  

¡Las contribuciones son bienvenidas!  

1. Haz un **fork** del proyecto  
2. Crea una nueva rama:  
```bash
git checkout -b feature/NuevaFuncionalidad
```  
3. Realiza tus cambios y haz commit:  
```bash
git commit -m "Agrega nueva funcionalidad"
```  
4. Pushea tu rama:  
```bash
git push origin feature/NuevaFuncionalidad
```  
5. Abre un **Pull Request** 🚀  

