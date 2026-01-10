# analisis_vivo_core_websockets.py
# Versión WebSocket del modo "Análisis en Vivo"
# Reemplaza completamente al antiguo analisis_vivo_core.py (UDP)

from collections import deque
import csv
from datetime import datetime
from zoneinfo import ZoneInfo
import os
from flask_socketio import SocketIO

LOCAL_TZ = ZoneInfo("America/Argentina/Salta")

def now_local():
    return datetime.now(LOCAL_TZ)

# Configuración
MAX_LEN = 50  # puntos visibles en el gráfico en vivo

# Buffers para el gráfico en tiempo real (se envían al frontend)
live_data = {
    "timestamps": deque(maxlen=MAX_LEN),
    "yaw": deque(maxlen=MAX_LEN),
    "pitch": deque(maxlen=MAX_LEN),
    "roll": deque(maxlen=MAX_LEN)
}

# Variables para grabación CSV
csv_writer = None
csv_file = None
act_writer = None
act_file = None

actividad_actual = None
inicio_actual = None

# Necesitamos acceso al socketio desde app.py
socketio: SocketIO = None  # Se asignará desde app.py


def set_socketio_instance(sio: SocketIO):
    """Llamar desde app.py para inyectar la instancia de SocketIO"""
    global socketio
    socketio = sio


def iniciar_grabacion(nombre_sesion="mpu_data"):
    """Crea los archivos CSV y prepara la grabación"""
    global csv_file, csv_writer, act_file, act_writer
    
    # Si había algo abierto por error, lo cerramos antes de abrir uno nuevo
    detener_grabacion()

    timestamp = now_local().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{nombre_sesion}_{timestamp}.csv"
    act_filename = f"Notas_{nombre_sesion}_{timestamp}.csv"
    
    os.makedirs("grabaciones_vivo", exist_ok=True)
    
    csv_path = os.path.join("grabaciones_vivo", csv_filename)
    act_path = os.path.join("grabaciones_vivo", act_filename)
    
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["Timestamp", "Yaw", "Pitch", "Roll", "Ax", "Ay", "Az"])
    
    act_file = open(act_path, "w", newline="", encoding="utf-8")
    act_writer = csv.writer(act_file)
    act_writer.writerow(["inicio", "fin", "actividad"])
    
    print(f"Grabación iniciada: {csv_filename}")
    return csv_filename


def registrar_actividad(descripcion):
    """Registra o cambia la actividad actual"""
    global actividad_actual, inicio_actual, act_writer, act_file
    
    # Validación extra
    if not act_file or not act_writer:
        return
    
    ahora = now_local()
    
    if actividad_actual is not None:
        # Cerrar actividad anterior
        try:
            act_writer.writerow([
                inicio_actual.strftime("%H:%M:%S.%f")[:-3],
                ahora.strftime("%H:%M:%S.%f")[:-3],
                actividad_actual
            ])
            act_file.flush()
        except: pass
    
    # Iniciar nueva
    actividad_actual = descripcion
    inicio_actual = ahora
    print(f"Nueva actividad: {descripcion}")


def procesar_datos_ws(data_str: str):
    """
    Se llama cada vez que llega un mensaje WebSocket desde el ESP.
    data_str es el JSON que envía el ESP: {"y":.., "p":.., "r":.., "ax":.., "ay":.., "az":..}
    """
    import json
    global csv_writer, csv_file
    try:
        datos = json.loads(data_str)
        yaw = float(datos.get("y", 0))
        pitch = float(datos.get("p", 0))
        roll = float(datos.get("r", 0))
        ax = float(datos.get("ax", 0))
        ay = float(datos.get("ay", 0))
        az = float(datos.get("az", 0))
        
        timestamp = now_local().strftime("%H:%M:%S.%f")[:-3]
        
        # Actualizar buffer para gráfico en vivo
        live_data["timestamps"].append(timestamp)
        live_data["yaw"].append(yaw)
        live_data["pitch"].append(pitch)
        live_data["roll"].append(roll)
        
        # Guardar en CSV si está grabando
        if csv_writer and csv_file and not csv_file.closed:
            csv_writer.writerow([timestamp, yaw, pitch, roll, ax, ay, az])
            #csv_file.flush()
        
        # Emitir datos actualizados a TODOS los clientes conectados al frontend
        if socketio:
            socketio.emit('datos_vivo', obtener_datos_vivo())
            
    except Exception as e:
        print(f"Error procesando datos WS: {e}")


def detener_grabacion():
    """Cierra archivos y registra la última actividad si está abierta"""
    global actividad_actual, inicio_actual, csv_file, act_file, csv_writer, act_writer
    
    if actividad_actual is not None and act_file and not act_file.closed and act_writer:
        ahora = datetime.now()
        try:
            act_writer.writerow([
                inicio_actual.strftime("%H:%M:%S.%f")[:-3],
                ahora.strftime("%H:%M:%S.%f")[:-3],
                actividad_actual
            ])
            act_file.flush()
        except ValueError:
            pass # Archivo ya estaba cerrado
    
    if csv_file:
        try:
            csv_file.close()
        except: pass
    if act_file:
        try:
            act_file.close()
        except: pass

    # Ponemos todo en None para que procesar_datos_ws sepa que no debe escribir
    csv_file = None
    csv_writer = None
    act_file = None
    act_writer = None
    actividad_actual = None
    
    print("Grabación detenida y archivos cerrados.")
    
    # Limpiar buffers
    for key in live_data:
        live_data[key].clear()
    
    # Opcional: notificar al frontend que se detuvo
    if socketio:
        socketio.emit('grabacion_detenida')


def obtener_datos_vivo():
    """Devuelve los datos actuales del buffer para el gráfico"""
    return {
        "labels": list(live_data["timestamps"]),
        "yaw": list(live_data["yaw"]),
        "pitch": list(live_data["pitch"]),
        "roll": list(live_data["roll"])
    }