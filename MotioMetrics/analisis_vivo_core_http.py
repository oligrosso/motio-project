# analisis_vivo_core.py
# Reutiliza la lógica de leer_datos.py para el modo "Análisis en Vivo"
# Se ejecuta en un thread dentro de Flask

import socket
from collections import deque
import csv
from datetime import datetime
import os

# Configuración fija (igual que en leer_datos.py)
UDP_IP = "0.0.0.0"
UDP_PORT = 4210
MAX_LEN = 50  # puntos en el gráfico en vivo

# Buffers para datos en tiempo real (los mismos que envías al frontend)
live_data = {
    "timestamps": deque(maxlen=MAX_LEN),
    "yaw": deque(maxlen=MAX_LEN),
    "pitch": deque(maxlen=MAX_LEN),
    "roll": deque(maxlen=MAX_LEN)
}

# Variables para CSV y anotaciones (se crean cuando se inicia la grabación)
csv_writer = None
csv_file = None
act_writer = None
act_file = None

actividad_actual = None
inicio_actual = None

# Cerca del inicio del archivo
running_udp = False

def iniciar_grabacion(nombre_sesion="mpu_data"):
    """Crea los archivos CSV y prepara todo para grabar"""
    global csv_file, csv_writer, act_file, act_writer
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{nombre_sesion}_{timestamp}.csv"
    act_filename = f"Notas_{nombre_sesion}_{timestamp}.csv"
    
    # Crear carpeta si no existe
    os.makedirs("grabaciones_vivo", exist_ok=True)
    
    csv_path = os.path.join("grabaciones_vivo", csv_filename)
    act_path = os.path.join("grabaciones_vivo", act_filename)
    
    csv_file = open(csv_path, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["Timestamp", "Yaw", "Pitch", "Roll", "Ax", "Ay", "Az"])
    
    act_file = open(act_path, "w", newline="")
    act_writer = csv.writer(act_file)
    act_writer.writerow(["inicio", "fin", "actividad"])
    
    print(f"Grabación iniciada: {csv_filename}")
    return csv_filename  # para devolver al frontend si querés

def registrar_actividad(descripcion):
    """Registra una nueva actividad (igual que en leer_datos.py)"""
    global actividad_actual, inicio_actual
    
    ahora = datetime.now()
    
    if actividad_actual is not None:
        # Cerrar la anterior
        act_writer.writerow([
            inicio_actual.strftime("%H:%M:%S.%f")[:-3],
            ahora.strftime("%H:%M:%S.%f")[:-3],
            actividad_actual
        ])
        act_file.flush()
    
    # Iniciar nueva
    actividad_actual = descripcion
    inicio_actual = ahora
    print(f"Nueva actividad: {descripcion}")

def udp_listener():
    """Escucha UDP y actualiza buffers + escribe CSV"""
    global running_udp, csv_writer
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)
    
    print("Escuchando UDP para análisis en vivo...")
    
    running_udp = True
    while running_udp:  # se detiene cuando se cierra el thread desde app.py
        try:
            data, addr = sock.recvfrom(1024)
            valores = data.decode('utf-8').strip().split(',')
            if len(valores) < 6:
                continue
                
            yaw = float(valores[0])
            pitch = float(valores[1])
            roll = float(valores[2])
            ax = float(valores[3])
            ay = float(valores[4])
            az = float(valores[5])
            
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # Actualizar buffers para frontend
            live_data["timestamps"].append(timestamp)
            live_data["yaw"].append(yaw)
            live_data["pitch"].append(pitch)
            live_data["roll"].append(roll)
            
            # Escribir en CSV si está grabando
            if csv_writer:
                csv_writer.writerow([timestamp, yaw, pitch, roll, ax, ay, az])
                csv_file.flush()
                
        except BlockingIOError:
            continue  # no hay datos, sigue esperando
        except Exception as e:
            print(f"Error UDP vivo: {e}")
            break
    
    sock.close()

def detener_grabacion():
    """Cierra archivos y última actividad"""
    global actividad_actual, inicio_actual, csv_file, act_file, running_udp
    running_udp = False
    
    if actividad_actual is not None:
        ahora = datetime.now()
        act_writer.writerow([
            inicio_actual.strftime("%H:%M:%S.%f")[:-3],
            ahora.strftime("%H:%M:%S.%f")[:-3],
            actividad_actual
        ])
        act_file.flush()
    
    if csv_file:
        csv_file.close()
    if act_file:
        act_file.close()
    
    print("Grabación detenida y archivos cerrados.")
    
    # Limpiar buffers
    for key in live_data:
        live_data[key].clear()

# Función para obtener datos actuales (usada por el endpoint poll)
def obtener_datos_vivo():
    return {
        "labels": list(live_data["timestamps"]),
        "yaw": list(live_data["yaw"]),
        "pitch": list(live_data["pitch"]),
        "roll": list(live_data["roll"])
    }