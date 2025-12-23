import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime
import warnings

from scipy.signal import butter, filtfilt
from spectrum import pburg
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay, accuracy_score, precision_score, recall_score, f1_score

# Ignorar advertencias de métricas si faltan datos (división por cero)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# ==========================================
# 1. FUNCIONES DE CARGA Y FILTRADO
# ==========================================

def cargar_datos(path):
    df = pd.read_csv(path, sep=",", encoding="latin1", on_bad_lines="skip")
    df = df.iloc[:-1]
    df.columns = df.columns.str.strip()

    # Convertir Timestamp
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Limpiar numéricos
    cols_num = ['Yaw', 'Pitch', 'Roll', 'Ax', 'Ay', 'Az']
    for col in cols_num:
        df[col] = pd.to_numeric(df[col].astype(str).str.strip(), errors='coerce')
    
    df = df.dropna(subset=cols_num)

    # Calcular SR
    diffs = (df['Timestamp']).diff().dropna().dt.total_seconds()
    diffs = diffs[diffs > 0]
    SR = int(round(1 / diffs.mean()))

    return df, SR

def pasa_altos_iir(signal, SR, fc=0.25):
    b, a = butter(1, fc / (SR / 2), btype='high')
    return filtfilt(b, a, signal)

def pasa_bajos_iir(signal, SR, fc=3.5):
    b, a = butter(8, fc / (SR / 2), btype='low')
    return filtfilt(b, a, signal)

def pasa_bandas_iir(signal, SR, flow, fhigh):
    b, a = butter(4, [flow / (SR / 2), fhigh / (SR / 2)], btype='band')
    return filtfilt(b, a, signal)

# ==========================================
# 2. PROCESAMIENTO Y VENTANEO
# ==========================================

def ventaneo_movil(signal, window_size, step):
    windows = []
    centers = []
    # Vectorización posible, pero el bucle es claro para ventanas superpuestas
    for start in range(0, len(signal) - window_size + 1, step):
        end = start + window_size
        windows.append(signal[start:end])
        centers.append(start + window_size // 2)
    return np.array(windows), np.array(centers)

def unificar_y_limpiar_episodios(temblores_bool, SR, min_gap_sec=0.5, min_duration_sec=2.0):
    arr = np.array(temblores_bool, dtype=bool)
    n = len(arr)
    
    # 1. Gap Filling (Unir huecos)
    gap_samples = int(min_gap_sec * SR)
    is_false = ~arr
    padded = np.concatenate(([True], is_false, [True])) 
    diff = np.diff(padded.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    
    for s, e in zip(starts, ends):
        if 0 < (e - s) <= gap_samples:
            if s > 0 and e < n:
                arr[s:e] = True 

    # 2. Eliminar episodios cortos
    min_samples = int(min_duration_sec * SR)
    padded = np.concatenate(([False], arr, [False]))
    diff = np.diff(padded.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    
    for s, e in zip(starts, ends):
        if (e - s) < min_samples:
            arr[s:e] = False 

    return arr

def suavizar_por_votacion(temblores_bool, SR, window_sec=0.5, umbral_voto=0.2):
    """Aplica media móvil para reducir ruido de alta frecuencia en la detección"""
    s = pd.Series(temblores_bool)
    w_samples = int(window_sec * SR)
    rolling_mean = s.rolling(window=w_samples, center=True, min_periods=1).mean()
    return (rolling_mean > umbral_voto).values

def metodo_burg_umbralizado(window, SR):
    # Parámetros Burg
    order = 6
    burg = pburg(window, order=order)
    psd = np.asarray(burg.psd)
    freqs = np.linspace(0, SR/2, len(psd))

    # Buscar picos
    idx_max = np.argmax(psd)
    f_dom = freqs[idx_max]
    
    # Corrección si el pico es 0Hz
    if f_dom == 0 and len(psd) > 1:
        idx_sorted = np.argsort(psd)
        idx_max = idx_sorted[-2]
        f_dom = freqs[idx_max]

    # Normalización
    psd_sum = np.sum(psd)
    psd_norm = psd / (psd_sum + 1e-12)
    amp_dom = psd_norm[idx_max]

    # Criterio de detección
    temblor = False
    if 3.5 < f_dom < 6 and amp_dom > 0.03: # Umbral ajustado a 0.03
        temblor = True

    return temblor, f_dom, amp_dom

def detectar_temblor(df, SR, window_sec, step_samples, mostrar_pasos=False):
    # 1. Filtro Pasa Altos (Eliminar deriva)
    yaw_filtered = pasa_altos_iir(df['Yaw'], SR)
    pitch_filtered = pasa_altos_iir(df['Pitch'], SR)
    roll_filtered = pasa_altos_iir(df['Roll'], SR)

    df_filtered = pd.DataFrame({
        'Timestamp': df['Timestamp'],
        'Yaw': yaw_filtered, 'Pitch': pitch_filtered, 'Roll': roll_filtered
    })

    # 2. Definición de Ventana
    window_size = int(window_sec * SR)
    
    # Ventaneo
    yaw_win, yaw_centers = ventaneo_movil(yaw_filtered, window_size, step_samples)
    pitch_win, pitch_centers = ventaneo_movil(pitch_filtered, window_size, step_samples)
    roll_win, roll_centers = ventaneo_movil(roll_filtered, window_size, step_samples)

    # 3. Análisis Burg por ventana
    temblores_yaw, temblores_pitch, temblores_roll = [], [], []

    # Iteramos sobre ventanas (asumiendo misma longitud para los 3 ejes)
    for i in range(len(yaw_win)):
        t_y, f_y, a_y = metodo_burg_umbralizado(yaw_win[i], SR)
        t_p, f_p, a_p = metodo_burg_umbralizado(pitch_win[i], SR)
        t_r, f_r, a_r = metodo_burg_umbralizado(roll_win[i], SR)

        temblores_yaw.append((t_y, f_y, a_y))
        temblores_pitch.append((t_p, f_p, a_p))
        temblores_roll.append((t_r, f_r, a_r))

    # 4. Post-Procesamiento (Limpieza y Votación)
    raw_yaw = [x[0] for x in temblores_yaw]
    raw_pitch = [x[0] for x in temblores_pitch]
    raw_roll = [x[0] for x in temblores_roll]

    # A. Votación para suavizar
    voted_yaw = suavizar_por_votacion(raw_yaw, SR, window_sec=1.0)
    voted_pitch = suavizar_por_votacion(raw_pitch, SR, window_sec=1.0)
    voted_roll = suavizar_por_votacion(raw_roll, SR, window_sec=1.0)

    # B. Gap Filling
    clean_yaw = unificar_y_limpiar_episodios(voted_yaw, SR, min_gap_sec=1.0)
    clean_pitch = unificar_y_limpiar_episodios(voted_pitch, SR, min_gap_sec=1.0)
    clean_roll = unificar_y_limpiar_episodios(voted_roll, SR, min_gap_sec=1.0)

    # Reconstrucción de tuplas para mantener datos de freq/amp
    temblores_yaw_limpios = [(clean_yaw[i], temblores_yaw[i][1], temblores_yaw[i][2]) for i in range(len(clean_yaw))]
    temblores_pitch_limpios = [(clean_pitch[i], temblores_pitch[i][1], temblores_pitch[i][2]) for i in range(len(clean_pitch))]
    temblores_roll_limpios = [(clean_roll[i], temblores_roll[i][1], temblores_roll[i][2]) for i in range(len(clean_roll))]

    # 5. Combinación de Ejes
    temblores_global = []
    for i in range(len(clean_yaw)):
        if clean_yaw[i] or clean_pitch[i] or clean_roll[i]:
            # Actualizamos individuales a True para la gráfica
            temblores_yaw_limpios[i] = (True, temblores_yaw_limpios[i][1], temblores_yaw_limpios[i][2])
            temblores_pitch_limpios[i] = (True, temblores_pitch_limpios[i][1], temblores_pitch_limpios[i][2])
            temblores_roll_limpios[i] = (True, temblores_roll_limpios[i][1], temblores_roll_limpios[i][2])
            temblores_global.append(True)
        else:
            temblores_global.append(False)

    return (temblores_global, df_filtered, 
            temblores_yaw_limpios, temblores_pitch_limpios, temblores_roll_limpios, 
            yaw_centers, pitch_centers, roll_centers)

def cuantificar_temblor(df, SR, temblores, centers, window_size, graph=False):
    yaw_band = pasa_bandas_iir(df['Yaw'], SR, 3.5, 6)
    pitch_band = pasa_bandas_iir(df['Pitch'], SR, 3.5, 6)
    roll_band = pasa_bandas_iir(df['Roll'], SR, 3.5, 6)
    
    rms_ypr = np.sqrt(yaw_band**2 + pitch_band**2 + roll_band**2)
    
    episodios = []
    in_episode = False
    start_win = 0
    half_win = window_size // 2
    N = len(df)

    # Agregar False al final para cerrar episodio pendiente
    temblores_pad = temblores + [False]

    for i, t in enumerate(temblores_pad):
        if t and not in_episode:
            in_episode = True
            start_win = i
        elif not t and in_episode:
            in_episode = False
            end_win = i - 1
            
            # Manejo de índices seguro
            if start_win < len(centers) and end_win < len(centers):
                ini_idx = max(0, centers[start_win] - half_win)
                fin_idx = min(N-1, centers[end_win] + half_win)
                
                inicio_ts = df['Timestamp'].iloc[ini_idx]
                fin_ts = df['Timestamp'].iloc[fin_idx]
                
                rms_seg = rms_ypr[ini_idx:fin_idx+1]
                amp_ep = np.max(rms_seg) if len(rms_seg) > 0 else 0
                episodios.append((inicio_ts, fin_ts, amp_ep))

    return rms_ypr, episodios

# ==========================================
# 3. EVALUACIÓN Y MÉTRICAS
# ==========================================

def evaluar_deteccion_temblor(df, anotaciones, temblores_pred, centers_indices):
    """
    Evalúa usando los centros exactos devueltos por la detección.
    Garantiza que y_true y y_pred tengan la misma longitud.
    """
    condiciones_temblor = ["Reposo", "Postural", "NarizReposo", "IntentoPostural", "postural", "reposo"]
    
    # Recuperar Timestamps de las ventanas analizadas
    timestamps_centers = df['Timestamp'].iloc[centers_indices].values
    y_true = np.zeros(len(temblores_pred), dtype=int)
    
    if anotaciones is not None and not anotaciones.empty:
        # Normalizar fechas de anotaciones
        fecha_ref = pd.to_datetime(df['Timestamp'].iloc[0]).date()
        
        def normalize_time(t):
            if pd.isnull(t): return t
            ts = pd.to_datetime(t, format='%H:%M:%S.%f', errors='coerce')
            return pd.Timestamp.combine(fecha_ref, ts.time()) if pd.notnull(ts) else ts

        anotaciones['inicio'] = anotaciones['inicio'].apply(normalize_time)
        anotaciones['fin'] = anotaciones['fin'].apply(normalize_time)

        for _, row in anotaciones.iterrows():
            actividad = str(row.get('actividad', '')).strip()
            grado = row.get('grado', 0)
            
            if actividad in condiciones_temblor and pd.notnull(grado) and grado > 0:
                mask = (timestamps_centers >= row['inicio']) & (timestamps_centers <= row['fin'])
                y_true[mask] = 1

    return y_true, np.array(temblores_pred, dtype=int)

# ==========================================
# 4. VISUALIZACIÓN
# ==========================================

def graficar_temblor_coloreado(df, SR, temblores_yaw, temblores_pitch, temblores_roll,
                               yaw_centers, pitch_centers, roll_centers, window_size,
                               rms=None, episodios=None, anotaciones=None):
    
    # Preparar fecha base
    df = df.copy()
    base_date = datetime.datetime.today().date()
    df['Timestamp'] = pd.to_datetime(df['Timestamp']).apply(
        lambda x: x.replace(year=base_date.year, month=base_date.month, day=base_date.day))

    n_rows = 4 if rms is not None else 3
    
    figsize = (14, 8) if rms is not None else (12, 8)
    fig, axes = plt.subplots(n_rows + 1, 1, figsize=figsize, sharex=True,
                             gridspec_kw={'height_ratios': [0.15] + [1]*n_rows})

    # Asignar ejes
    ax_anno = axes[0]
    data_axes = {'Yaw': (axes[1], df['Yaw'], 'r', temblores_yaw, yaw_centers),
                 'Pitch': (axes[2], df['Pitch'], 'orange', temblores_pitch, pitch_centers),
                 'Roll': (axes[3], df['Roll'], 'green', temblores_roll, roll_centers)}
    
    if rms is not None:
        ax_rms = axes[4]
    
    # Graficar Ejes Principales
    for name, (ax, data, color, temblores, centers) in data_axes.items():
        ax.plot(df['Timestamp'], data, label=name, color=color, linewidth=1.5)
        ax.set_ylabel(f'{name} (°)')
        # Grid mayor (línea sólida suave)
        ax.grid(True, which='major', linestyle='-', alpha=0.6)
        # Grid menor (línea punteada fina)
        ax.grid(True, which='minor', linestyle=':', alpha=0.3)
        ax.legend(loc='upper right')
        
        # Colorear fondo detección
        for i, (is_tremor, _, _) in enumerate(temblores):
            if is_tremor:
                c_idx = centers[i]
                # ini = df['Timestamp'].iloc[max(0, c_idx - window_size//2)]
                # fin = df['Timestamp'].iloc[min(len(df)-1, c_idx + window_size//2)]
                # ax.axvspan(ini, fin, color='red', alpha=0.1, lw=0) 

    # Colorear episodios consolidados (más limpio)
    if episodios:
        for ini, fin, amp in episodios:
            ini, fin = pd.to_datetime(ini), pd.to_datetime(fin)
            for ax in [axes[1], axes[2], axes[3]]:
                ax.axvspan(ini, fin, color='#ffcccc', alpha=0.5, lw=0)
            if rms is not None:
                ax_rms.axvspan(ini, fin, color='#ffcccc', alpha=0.5, lw=0)

    # Graficar RMS
    if rms is not None:
        ax_rms.plot(df['Timestamp'], rms, label='RMS Combinado', color='blue', linewidth=1)
        ax_rms.set_ylabel('RMS')
        ax_rms.legend(loc='upper right')
        
        # Grids también para RMS
        ax_rms.grid(True, which='major', linestyle='-', alpha=0.6)
        ax_rms.grid(True, which='minor', linestyle=':', alpha=0.3)
        
        ax_rms.set_ylim(bottom=0)
        if episodios:
            y_lim = ax_rms.get_ylim()[1]
            for ini, fin, amp in episodios:
                ax_rms.text(fin, y_lim, f'Amp: {amp:.2f}', ha='right', va='top',
                            color="blue", fontsize=7, fontweight='bold',
                            bbox=dict(facecolor='white', edgecolor='none', pad=1.5))

    # Anotaciones Médicas
    ax_anno.set_yticks([])
    ax_anno.spines[['top', 'right', 'left', 'bottom']].set_visible(False)
    
    activity_boundaries = []
    if anotaciones is not None:
        ann = anotaciones.copy()
        # Ajuste fecha anotaciones
        ann['inicio'] = pd.to_datetime(ann['inicio'], format='%H:%M:%S.%f').apply(lambda x: x.replace(year=base_date.year, month=base_date.month, day=base_date.day))
        ann['fin'] = pd.to_datetime(ann['fin'], format='%H:%M:%S.%f').apply(lambda x: x.replace(year=base_date.year, month=base_date.month, day=base_date.day))
        
        for _, row in ann.iterrows():
            ax_anno.axvspan(row['inicio'], row['fin'], color='gray', alpha=0.3)
            ax_anno.text(row['inicio'] + (row['fin'] - row['inicio'])/2, 0.5, 
                         row.get('actividad', ''), ha='center', va='center', fontsize=9)
            activity_boundaries.extend([row['inicio'], row['fin']])

    data_axes = [axes[1], axes[2], axes[3]]
    if rms is not None:
        data_axes.append(axes[4])

    for i, ax in enumerate(data_axes):
        # 1. Formato de texto: Hora:Minuto:Segundo
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        
        # 2. Ticks MAYORES (Líneas fuertes CON etiqueta de texto)
        # interval=5 -> Muestra la hora cada 5 segundos.
        # Puedes cambiarlo a 10 si se ve muy amontonado.
        ax.xaxis.set_major_locator(mdates.SecondLocator(interval=5)) 
        
        # 3. Ticks MENORES (Líneas finas SIN etiqueta, solo para ver el segundo exacto)
        # interval=1 -> Una rayita cada 1 segundo
        ax.xaxis.set_minor_locator(mdates.SecondLocator(interval=1))
        
        # 4. Configurar la Grilla (Cuadrícula)
        ax.grid(True, which='major', linestyle='-', linewidth=0.8, alpha=0.5) # Línea fuerte
        ax.grid(True, which='minor', linestyle=':', linewidth=0.5, alpha=0.3) # Línea fina

        # 5. Rotar etiquetas 45 grados para que entren bien
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
        
        # 6. Dibujar líneas negras de separación de actividades
        for t in activity_boundaries:
            ax.axvline(t, color='black', linestyle='--', linewidth=0.8, alpha=0.8)

    # Solo agregamos la etiqueta "Tiempo" al último gráfico de abajo
    data_axes[-1].set_xlabel("Tiempo (HH:MM:SS)", fontsize=10, fontweight='bold')

    plt.tight_layout()
    
    # ⚠️ IMPORTANTE: Esto fuerza a que se vean las etiquetas en TODOS los subplots
    # Si solo quieres ver la hora abajo de todo, borra estas dos líneas siguientes:
    for ax in data_axes:
        plt.setp(ax.get_xticklabels(), visible=True)

    plt.show()

def graficar_matriz_confusion(y_true, y_pred, titulo="Matriz de Confusión"):
    # Force labels to avoid 1x1 matrix error
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=["No Temblor", "Temblor"])
    disp.plot(cmap="Blues", values_format="d", colorbar=False, ax=ax1)
    ax1.set_title(titulo)
    
    ax2.axis("off")
    metrics_text = (f"Métricas:\n\n"
                    f"Accuracy:  {acc:.3f}\n"
                    f"Precision: {prec:.3f}\n"
                    f"Recall:    {rec:.3f}\n"
                    f"F1-score:  {f1:.3f}")
    ax2.text(0.1, 0.5, metrics_text, fontsize=12, va="center", family="monospace")
    
    plt.tight_layout()
    plt.show()

def frecuencia_temblor(df, episodios, SR):
    """
    Calcula la frecuencia dominante promedio de los episodios de temblor detectados.
    
    Parámetros:
    - df: DataFrame con columnas 'Timestamp', 'Yaw', 'Pitch', 'Roll'.
    - episodios: Lista de tuplas (inicio_ts, fin_ts, amplitud).
    - SR: Frecuencia de muestreo (Sampling Rate).
    
    Retorna:
    - frecuencias: Lista de frecuencias dominantes por episodio individual.
    - f_dom_mean: Frecuencia dominante del espectro promedio global.
    """
    
    if not episodios:
        print("⚠️ No hay episodios para analizar frecuencia.")
        return [], 0.0
    
    # 1. Copiar y Pre-filtrar (Pasa altos a 0.5Hz para limpiar deriva)
    df_clean = df.copy()
    for axis in ['Yaw', 'Pitch', 'Roll']:
        df_clean[axis] = pasa_altos_iir(df_clean[axis], SR, fc=1.5)

    todas_psd = []
    frecuencias_individuales = []

    # 2. Recorrer cada episodio detectado
    for (inicio_ts, fin_ts, _) in episodios:
        
        # Buscar índices de tiempo (asumiendo Timestamp ordenado)
        # Nota: Usamos máscaras booleanas para robustez
        mask = (df_clean['Timestamp'] >= inicio_ts) & (df_clean['Timestamp'] <= fin_ts)
        segmento_df = df_clean.loc[mask]
        
        if segmento_df.empty:
            continue

        # Promediar los 3 ejes para tener una señal compuesta de movimiento
        # (Yaw + Pitch + Roll) / 3
        segmento_signal = (
            segmento_df['Yaw'] + segmento_df['Pitch'] + segmento_df['Roll']
        ) / 3.0

        # Validación: Necesitamos suficientes puntos para Burg
        if len(segmento_signal) < 4: 
            continue

        # 3. Calcular Espectro de Burg
        order = min(6, len(segmento_signal) - 1) # El orden no puede ser mayor que las muestras
        try:
            burg = pburg(segmento_signal.values, order=order)
            psd = np.asarray(burg.psd)
            
            # Guardamos PSD y calculamos frecuencia local
            todas_psd.append(psd)
            
            freqs = np.linspace(0, SR/2, len(psd))
            idx_max = np.argmax(psd)
            frecuencias_individuales.append(freqs[idx_max])
            
        except Exception as e:
            print(f"Error calculando Burg en episodio: {e}")
            continue

    if not todas_psd:
        print("No se pudieron calcular espectros válidos.")
        return [], 0.0

    # 4. Promediar Espectros (Normalizando longitudes)
    # Como los episodios tienen distinta duración, las PSD tienen distinto largo.
    # Interpolamos todos a una longitud común.
    len_min = min(len(p) for p in todas_psd)
    freqs_comunes = np.linspace(0, SR/2, len_min)

    psd_interp_list = []
    for psd in todas_psd:
        freqs_original = np.linspace(0, SR/2, len(psd))
        # Interpolar al eje común
        psd_resampled = np.interp(freqs_comunes, freqs_original, psd)
        psd_interp_list.append(psd_resampled)

    # Promedio
    psd_mean = np.mean(psd_interp_list, axis=0)

    # 5. Frecuencia Dominante Global
    idx_max_global = np.argmax(psd_mean)
    f_dom_mean = freqs_comunes[idx_max_global]

    # 6. Graficar
    plt.figure(figsize=(7, 4))
    plt.plot(freqs_comunes, psd_mean, label='PSD Promedio (Burg)', color='b')
    plt.axvline(f_dom_mean, color='r', linestyle='--', label=f'Frec. Dominante: {f_dom_mean:.2f} Hz')
    plt.scatter([f_dom_mean], [psd_mean[idx_max_global]], color='r', zorder=5)
    
    plt.xlabel("Frecuencia (Hz)")
    plt.ylabel("Densidad Espectral de Potencia (PSD)")
    plt.xlim(0, min(15, SR/2)) # Enfocamos en rango de temblor (0-15Hz)
    plt.title("Espectro Promedio de Episodios de Temblor")
    plt.legend()
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.show()

    return frecuencias_individuales, f_dom_mean
# ==========================================
# 5. BLOQUE PRINCIPAL (MAIN)
# ==========================================

if __name__ == "__main__":
    
    # === CONFIGURACIÓN ===
    BASE_DIR = "/Users/alexasessarego/Documents"
    PACIENTE = "mpu_data08"
    # ----------------------------------------------------
    # AQUÍ DEFINES EL TAMAÑO Y PASO UNA SOLA VEZ:
    DURACION_VENTANA_SEG = 3  # Tamaño de ventana en segundos
    STEP_MUESTRAS = 1         # Paso en muestras (1 = máxima precisión)
    # ----------------------------------------------------

    # 1. Rutas
    path_datos = os.path.join(BASE_DIR, f"{PACIENTE}.csv")
    path_notas = os.path.join(BASE_DIR, f"Notas_{PACIENTE}.csv")

    # 2. Cargar Datos
    if not os.path.exists(path_datos):
        print(f"Error: No se encuentra {path_datos}")
        exit()
        
    df, SR = cargar_datos(path_datos)
    print(f"Paciente: {PACIENTE} | SR: {SR} Hz")

    if os.path.exists(path_notas):
        anotaciones = pd.read_csv(path_notas)
    else:
        print("⚠️ No hay archivo de notas.")
        anotaciones = None

    # 3. Detectar (Pasamos los parámetros definidos arriba)
    # Nota: window_size se calculará dentro usando SR * DURACION_VENTANA_SEG
    temblores, df_filtered, ty, tp, tr, yc, pc, rc = detectar_temblor(
        df, SR, 
        window_sec=DURACION_VENTANA_SEG, 
        step_samples=STEP_MUESTRAS, 
        mostrar_pasos=False
    )

    # 4. Cuantificar (Calculamos window_size en pixeles para pasarle a esta función)
    window_size_samples = int(DURACION_VENTANA_SEG * SR)
    rms_ypr, episodios = cuantificar_temblor(
        df, SR, temblores, yc, 
        window_size=window_size_samples, 
        graph=False
    )

    # 5. Graficar Temblores
    graficar_temblor_coloreado(
        df_filtered, SR, ty, tp, tr, yc, pc, rc,
        window_size=window_size_samples,
        rms=rms_ypr, episodios=episodios, anotaciones=anotaciones
    )

    # 6. Analizar Frecuencia
    frecuencia_temblor(df, episodios, SR)

    # 7. Evaluar vs Notas Médicas
    # Pasamos 'temblores' y 'yc' (centros) para que la comparación sea exacta
    y_true, y_pred = evaluar_deteccion_temblor(df, anotaciones, temblores, centers_indices=yc)
    
    graficar_matriz_confusion(y_true, y_pred, titulo=f"Matriz de Confusión - {PACIENTE}")