from datetime import datetime


class SistemaAlertas:
    def __init__(self):
        self.alerta = False
        self.tipo = ''
        self.inicio = None
        self.log_interacciones = []
        self.justificacion = ''

    def activar(self, tipo):
        if not self.alerta:
            self.alerta = True
            self.tipo = tipo
            self.inicio = datetime.now()
            print(f"ALERTA: {tipo}")

    def desactivar(self):
        if self.alerta:
            self.alerta = False
            self.tipo = ''
            print("Alerta desactivada")

    def registrar(self, count):
        ahora = datetime.now()
        self.log_interacciones.append(ahora)

        # Mantener solo interacciones de los últimos 30 segundos
        self.log_interacciones = [t for t in self.log_interacciones if (ahora - t).seconds <= 30]

        # Activar alerta si hay suficientes interacciones en el período
        return len(self.log_interacciones) >= count