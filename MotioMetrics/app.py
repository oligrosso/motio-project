# === PRIMERO DE TODO: eventlet monkey_patch ===
import eventlet
eventlet.monkey_patch()
# =============================================
import os
import io
import csv
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
import scipy.signal as signal
from scipy.signal import butter, filtfilt, hilbert
from spectrum import pburg

# --- IMPORTS DE MÓDULOS PROPIOS ---
from analisis_core import cargar_datos, detectar_temblor, cuantificar_temblor, frecuencia_temblor
from analisis_vivo_core_websockets import (
    set_socketio_instance,
    iniciar_grabacion,
    registrar_actividad,
    detener_grabacion,
    obtener_datos_vivo,
    procesar_datos_ws
)

app = Flask(__name__)
CORS(app)

# --- SOCKETIO PARA WEBSOCKETS ---
socketio = SocketIO(app, cors_allowed_origins="*", allow_eio3=True)

# Inyectamos la instancia de SocketIO al módulo de análisis vivo
set_socketio_instance(socketio)

# --- NAMESPACE PARA DATOS DEL SENSOR ---
@socketio.on('connect')
def handle_connect():
    print("[WS] Sensor conectado al backend")

@socketio.on('disconnect')
def handle_disconnect():
    print("[WS] Sensor desconectado")

# El ESP envía mensajes de texto (JSON string)
@socketio.on('message')
def handle_sensor_data(data):
    # data es el string JSON que envía el ESP
    procesar_datos_ws(str(data))


# --- ENDPOINTS HTTP (para frontend y control) ---
@app.route('/api/leer_datos', methods=['POST'])
def leer_datos():
    """Control de grabación y polling de datos en vivo"""
    global csv_filename
    
    action = request.json.get('action')
    
    if action == 'start':
        nombre_sesion = request.json.get('nombre_sesion', 'sesion_vivo')
        csv_filename = iniciar_grabacion(nombre_sesion)
        return jsonify({"status": "started", "csv": csv_filename})
    
    elif action == 'stop':
        detener_grabacion()
        return jsonify({"status": "stopped", "csv": csv_filename or "no_csv"})
    
    elif action == 'anotacion':
        descripcion = request.json.get('descripcion')
        if descripcion:
            registrar_actividad(descripcion)
            return jsonify({"status": "anotacion_ok"})
        return jsonify({"error": "Falta descripción"}), 400
    
    elif action == 'poll':
        datos = obtener_datos_vivo()
        return jsonify(datos)
    
    return jsonify({"error": "Acción no válida"}), 400


# --- ANÁLISIS DE ARCHIVO CSV (sin cambios) ---
def procesar_csv_logic(stream):
    df, SR = cargar_datos(stream)
    temblores, tiene_temblor, df_filt, yaw, pitch, roll = detectar_temblor(df, SR)
    rms_ypr, episodios = cuantificar_temblor(df, SR, temblores)
    frecuencias, f_dom_mean, freqs_std, psd_mean = frecuencia_temblor(df, episodios, SR)

    psd_pico = np.max(psd_mean) if len(psd_mean) > 0 else 0

    factor_diezmo = 1 if len(df) < 1000 else int(len(df)/1000)

    episodios_list = []
    for inicio_ts, fin_ts, amp in episodios:
        episodios_list.append({
            "inicio": inicio_ts.strftime("%Y-%m-%d %H:%M:%S"),
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
            "rms": rms_ypr[::factor_diezmo].tolist() if len(rms_ypr) > 0 else [],
            "freq_x": freqs_std.tolist(),
            "freq_y": psd_mean.tolist(),
            "episodios": episodios_list
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
        stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
        resultados = procesar_csv_logic(stream)
        return jsonify(resultados)
    except Exception as e:
        print(f"Error procesando CSV: {e}")
        return jsonify({"error": str(e)}), 500


# --- HEALTH CHECK Y DESCARGA ---
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "MotioMetrics Backend (WebSocket mode) is running!",
        "endpoints": [
            "POST /api/leer_datos (start/stop/anotacion/poll)",
            "POST /api/analizar_datos",
            "WebSocket: /ws/ingresar_datos"
        ]
    })

@app.route('/grabaciones_vivo/<filename>')
def serve_csv(filename):
    response = send_from_directory('grabaciones_vivo', filename)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

# Crear carpeta al iniciar
if not os.path.exists('grabaciones_vivo'):
    os.makedirs('grabaciones_vivo')


# --- EJECUCIÓN ---
if __name__ == '__main__':    
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)