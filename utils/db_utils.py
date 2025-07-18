from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import bcrypt

# Configuración base
Base = declarative_base()
engine = create_engine("sqlite:///users.db", echo=True)
Session = sessionmaker(bind=engine)

# Definición del modelo
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    usuario = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    unidad = Column(String, nullable=False)
    chofer = Column(String, nullable=False)
    ip_camara = Column(String, nullable=False)

# Crear las tablas si no existen
def init_db():
    Base.metadata.create_all(engine)

# Función para crear un nuevo usuario
def create_user(usuario, password, unidad, chofer, ip_camara):
    session = Session()
    try:
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(
            usuario=usuario,
            password_hash=password_hash,
            unidad=unidad,
            chofer=chofer,
            ip_camara=ip_camara
        )
        session.add(user)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

# Verificar credenciales
def verify_user(usuario, password):
    session = Session()
    user = session.query(User).filter_by(usuario=usuario).first()
    session.close()
    if user:
        return bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8'))
    return False

# Obtener datos del usuario
def get_user_data(usuario):
    session = Session()
    user = session.query(User).filter_by(usuario=usuario).first()
    session.close()
    if user:
        return {
            "usuario": user.usuario,
            "unidad": user.unidad,
            "chofer": user.chofer,
            "ip_camara": user.ip_camara
        }
    return None

# Ejecutar si se llama directamente
if __name__ == "__main__":
    init_db()