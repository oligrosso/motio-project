import os
import io
import csv
import socket
import threading
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from collections import deque
from datetime import datetime
import scipy.signal as signal
from scipy.signal import butter, filtfilt, hilbert
from spectrum import pburg
from analisis_core import cargar_datos, pasa_altos_iir, pasa_bajos_iir, pasa_bandas_iir, ventaneo, metodo_burg_umbralizado, eliminar_ventanas_aisladas, eliminar_ventanas_aisladas_bool, detectar_episodios_no_mov, detectar_temblor, cuantificar_temblor, frecuencia_temblor
from analisis_vivo_core_http import iniciar_grabacion, registrar_actividad, detener_grabacion, obtener_datos_vivo, udp_listener
app = Flask(__name__)
CORS(app)  # Permite que GitHub Pages hable con Render

# --- LÓGICA DE ANÁLISIS EN VIVO (Adaptada de leer_datos_prueba.py) ---

# Buffer en memoria para datos en tiempo real
live_data = {
    "yaw": deque(maxlen=50),
    "pitch": deque(maxlen=50),
    "roll": deque(maxlen=50),
    "timestamps": deque(maxlen=50)
}
is_recording = False

# Para grabación en vivo
csv_filename = None  # Guardará el nombre del CSV generado
is_recording = False


#def udp_listener():
#    """Escucha datos UDP en segundo plano y actualiza el buffer"""
#    global is_recording
#    UDP_IP = "0.0.0.0"
#    UDP_PORT = 4210
#    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#    try:
#        sock.bind((UDP_IP, UDP_PORT))
#        sock.settimeout(1.0)
#        print(f"Escuchando UDP en {UDP_PORT}...")
#    except Exception as e:
#        print(f"Error bind UDP: {e}")
#        return

#    while is_recording:
#        try:
#            data, addr = sock.recvfrom(1024)
#            values = [float(x) for x in data.decode('utf-8').strip().split(',')]
#            # Asumiendo formato: Yaw, Pitch, Roll, Ax, Ay, Az
#            if len(values) >= 3:
#                timestamp = datetime.now().strftime("%H:%M:%S")
#                live_data["yaw"].append(values[0])
#                live_data["pitch"].append(values[1])
#                live_data["roll"].append(values[2])
#                live_data["timestamps"].append(timestamp)
#        except socket.timeout:
#            continue
#        except Exception as e:
#            print(f"Error recibiendo UDP: {e}")
#            break
#    sock.close()

# Nueva ruta para recibir datos (Sensor → Backend)
# Render no permite UDP. Esta ruta recibe el JSON que ahora envía tu .ino vía HTTP POST.
@app.route('/api/ingresar_datos', methods=['POST'])
def ingresar_datos():
    global is_recording
    data = request.json
    
    if not data:
        return jsonify({"error": "No data received"}), 400

    try:
        from analisis_vivo_core_http import live_data, csv_writer

        # 1. Normalizar: Si es un solo objeto, lo metemos en una lista
        puntos = data if isinstance(data, list) else [data]

        # 2. Procesar cada punto de la lista
        for punto in puntos:
            y = float(punto['y'])
            p = float(punto['p'])
            r = float(punto['r'])
            ax = float(punto.get('ax', 0))
            ay = float(punto.get('ay', 0))
            az = float(punto.get('az', 0))
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # Actualizar buffer para el gráfico en vivo
            live_data["timestamps"].append(ts)
            live_data["yaw"].append(y)
            live_data["pitch"].append(p)
            live_data["roll"].append(r)

            # Escribir en CSV si la grabación está activa
            if is_recording and csv_writer:
                csv_writer.writerow([ts, y, p, r, ax, ay, az])

        return jsonify({"status": "ok", "procesados": len(puntos)}), 200

    except Exception as e:
        print(f"Error procesando batch: {e}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/leer_datos', methods=['POST'])
def leer_datos():
    """Inicia/Detiene la escucha o devuelve datos actuales"""
    global is_recording, csv_filename
    
    action = request.json.get('action')
    
    if action == 'start': # el sensor "empuja" los datos hacia la nueva ruta /api/ingresar_datos.
        if not is_recording:
            is_recording = True
            
            # Iniciar grabación (crea CSV)
            nombre_sesion = request.json.get('nombre_sesion', 'sesion_vivo')
            csv_filename = iniciar_grabacion(nombre_sesion)
        return jsonify({"status": "started", "message": csv_filename})
    
    elif action == 'stop':
        if is_recording:
            is_recording = False
            detener_grabacion()  # Cierra CSV y última anotación
        return jsonify({"status": "stopped", "csv": csv_filename or "no_csv"})

    elif action == 'anotacion':
        descripcion = request.json.get('descripcion')
        if descripcion:
            registrar_actividad(descripcion)
        return jsonify({"status": "anotacion_ok"})

    #elif action == 'poll':
        # Devolver los datos actuales del buffer
    #    return jsonify({
    #        "labels": list(live_data["timestamps"]),
    #        "yaw": list(live_data["yaw"]),
    #        "pitch": list(live_data["pitch"]),
    #        "roll": list(live_data["roll"])
    #    })
    elif action == 'poll':
        datos = obtener_datos_vivo()
        return jsonify(datos)
    
    return jsonify({"error": "Acción no válida"}), 400

def procesar_csv_logic(stream):
    df, SR = cargar_datos(stream)
    # Llamadas a las nuevas funciones (reemplaza el filtro y FFT simple)
    temblores, tiene_temblor, df_filt, yaw, pitch, roll = detectar_temblor(df, SR) # funcion de analisis_core
    rms_ypr, episodios = cuantificar_temblor(df, SR, temblores) # funcion de analisis_core
    frecuencias, f_dom_mean, freqs_std, psd_mean = frecuencia_temblor(df, episodios, SR)  # Usamos df_filt

    # Métricas actualizadas con Burg
    psd_pico = np.max(psd_mean) if len(psd_mean) > 0 else 0

    # Datos para gráficos (diezmo si es grande)
    factor_diezmo = 1 if len(df) < 1000 else int(len(df)/1000)

    # <<< AQUÍ AGREGAMOS LOS EPISODIOS >>>
    episodios_list = []
    for inicio_ts, fin_ts, amp in episodios:
        episodios_list.append({
            "inicio": inicio_ts.strftime("%Y-%m-%d %H:%M:%S"),  # Ej: "2025-12-14 08:31:20"
            "fin":    fin_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "amplitud": round(float(amp), 2)
        })

    return {
        "metricas": {
            "frecuencia_dominante": round(float(f_dom_mean), 2),
            "psd_pico": round(float(psd_pico), 2),
            "sr": SR,
            "tiene_temblor": tiene_temblor
        },
        "graficos": {
            "tiempo": df['Timestamp'].astype(str).iloc[::factor_diezmo].tolist(),
            "rms": rms_ypr[::factor_diezmo].tolist() if len(rms_ypr) > 0 else [],  # RMS como antes
            "freq_x": freqs_std.tolist(),  # Ahora freqs_std de Burg
            "freq_y": psd_mean.tolist(),    # Ahora psd_mean de Burg
            "episodios": episodios_list # NUEVO: los rangos de temblor
        }
    }

@app.route('/api/analizar_datos', methods=['POST'])
def analizar_datos_endpoint():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    try:
        # Procesamos el archivo en memoria
        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        resultados = procesar_csv_logic(stream)
        return jsonify(resultados)
    except Exception as e:
        print(f"Error procesando CSV: {e}")
        return jsonify({"error": str(e)}), 500
    
# --- RUTA DE PRUEBA (Health Check) ---
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "MotioMetrics Backend is running!",
        "endpoints": [
            "POST /api/leer_datos",
            "POST /api/analizar_datos"
        ]
    })

@app.route('/api/ultimo_dato', methods=['GET'])
def ultimo_dato():
    from analisis_vivo_core_http import live_data
    if len(live_data["timestamps"]) > 0:
        return jsonify({
            "y": live_data["yaw"][-1],
            "p": live_data["pitch"][-1],
            "r": live_data["roll"][-1],
            "ax": 0, # Opcional: podrías guardar ax, ay, az en el buffer también
            "ay": 0,
            "az": 0,
            "ts": live_data["timestamps"][-1]
        })
    return jsonify({"error": "No hay datos aún"}), 404

from flask import send_from_directory

@app.route('/grabaciones_vivo/<filename>')
def serve_csv(filename):
    response = send_from_directory('grabaciones_vivo', filename)
    response.headers['Access-Control-Allow-Origin'] = '*' # PERMITIR DESCARGA DESDE GITHUB
    return response

# Asegúrate de que esta carpeta exista al arrancar
if not os.path.exists('grabaciones_vivo'):
    os.makedirs('grabaciones_vivo')

if __name__ == '__main__':
    # Puerto 5000 es el estándar, Render usará la variable de entorno PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
  