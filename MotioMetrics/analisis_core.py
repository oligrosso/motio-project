import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import scipy.signal as signal
from scipy.signal import butter, filtfilt, hilbert
from spectrum import pburg
import matplotlib.dates as mdates
import datetime as datetime
import datetime
import os

def cargar_datos(path):
    # Leer archivo
    df = pd.read_csv(path, sep=",", encoding="latin1", on_bad_lines="skip")
    df = df.iloc[:-1]
    df.columns = df.columns.str.strip()  # limpiar nombres

    # Convertir la columna 'Timestamp' a formato datetime
    # Intentamos primero con el formato de hora que usa el análisis en vivo
    try:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%H:%M:%S.%f')
    except ValueError:
        # Si falla (ej: archivo viejo con fecha), dejamos que pandas adivine
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    # Normalizar el tiempo para que comience en 0 segundos
    #df['Timestamp'] = (df['Timestamp'] - df['Timestamp'].iloc[0]).dt.total_seconds()


    # Limpiar y convertir columnas numéricas
    for col in ['Yaw','Pitch','Roll','Ax','Ay','Az']:
        df[col] = pd.to_numeric(df[col].astype(str).str.strip(), errors='coerce')

    # Eliminar filas con NaN en cualquiera de estas columnas
    df = df.dropna(subset=['Yaw','Pitch','Roll','Ax','Ay','Az'])

    diffs = (df['Timestamp']).diff().dropna()
    # Convertir diferencias de tiempo a segundos
    diffs = diffs.dt.total_seconds()

    # Filtrar diferencias válidas (mayores a 0)
    diffs = diffs[diffs > 0]

    # Calcular frecuencia de muestreo promedio
    SR = 1 / diffs.mean()
    SR = int(round(SR))
    if SR < 1: SR = 10 # Valor por defecto si el cálculo falla

    return  df, SR

def pasa_altos_iir(signal, SR, fc =0.25):
    # Seguridad: Si SR es 0 o NaN, devolver original
    if SR <= fc * 2:
        return signal
    # Diseño del filtro pasa altos
    fs = SR  # Frecuencia de muestreo
    w = fc / (fs / 2)  # Frecuencia normalizada
    # Asegurar que w esté estrictamente entre 0 y 1
    w = max(0.001, min(0.999, w))
    b, a = butter(1, w, btype='high')

    # Aplicar el filtro a la señal
    filtered_signal = filtfilt(b, a, signal)
    
    return filtered_signal

def pasa_bajos_iir(signal, SR, fc = 3.5):
    # Seguridad: Si SR es muy bajo, no podemos filtrar
    if SR <= fc * 2:
        return signal
    # Diseño del filtro pasa bajos
    fs = SR  # Frecuencia de muestreo
    w = fc / (fs / 2)  # Frecuencia normalizada
    w = max(0.001, min(0.999, w))
    b, a = butter(8, w, btype='low')

    # Aplicar el filtro a la señal
    filtered_signal = filtfilt(b, a, signal)
    
    return filtered_signal

def pasa_bandas_iir(signal, SR, flow, fhigh):
    # Seguridad crítica para cuantificar_temblor
    # Si SR < 15 (aprox), el filtro de 3.5-7.5 Hz fallará
    if SR <= fhigh * 2:
        # Si no podemos aplicar banda de temblor, aplicamos un pasa altos simple
        # para al menos quitar la gravedad y no devolver basura
        return pasa_altos_iir(signal, SR, fc=0.5)
    # Diseño del filtro pasa bandas
    fs = SR  # Frecuencia de muestreo
    lowcut = flow  # Frecuencia de corte baja
    highcut = fhigh # Frecuencia de corte alta
    w1 = lowcut / (fs / 2)  # Frecuencia normalizada
    w2 = highcut / (fs / 2)  # Frecuencia normalizada
    # Limitar valores para evitar el error Wn < 1
    w1 = max(0.001, min(0.998, w1))
    w2 = max(0.002, min(0.999, w2))
    b, a = butter(4, [w1, w2], btype='band')

    # Aplicar el filtro a la señal
    filtered_signal = filtfilt(b, a, signal)

    return filtered_signal

def ventaneo(signal, window_size, overlap):
    step = window_size - overlap
    windows = []
    for start in range(0, len(signal) - window_size + 1, step):
        windows.append(signal[start:start + window_size])
    return np.array(windows)

def metodo_burg_umbralizado(window, SR):
    temblor = False

    # Calcular el espectro de potencia usando el método de Burg
    order = 6  # Orden del modelo AR
    burg = pburg(window, order=order)
    psd = burg.psd
    freqs = np.linspace(0, SR/2, len(psd))

    f_dom = freqs[np.argmax(psd)]
    if f_dom == 0: #tomar el siguiente pico si el dominante es 0
        f_dom = freqs[np.argsort(psd)[-2]]
    
    #Normalizar el espectro de potencia
    psd_norm = psd / np.sum(psd)
    amp_dom = psd_norm[np.argmax(psd)]

    # Umbral para detectar temblor
    if f_dom < 7.5 and f_dom > 3.5 and amp_dom > 0.05:
        temblor = True

    return temblor, f_dom, amp_dom

def eliminar_ventanas_aisladas(temblores, min_consecutivos=2):
    """
    Elimina ventanas aisladas de detección de temblor.
    """
    temblores_limpios = temblores.copy()

    for i in range(len(temblores)):
        if temblores[i][0]:  # Si hay temblor en la ventana actual
            anterior = temblores[i-1][0] if i > 0 else False
            siguiente = temblores[i+1][0] if i < len(temblores)-1 else False
            if not anterior and not siguiente:
                temblores_limpios[i] = (False, temblores[i][1], temblores[i][2])
                
    return temblores_limpios

def eliminar_ventanas_aisladas_bool(mask, min_consecutivos=2):
    mask = mask.copy()
    count = 0
    for i, val in enumerate(mask + [False]):  # añadimos False para cerrar el último bloque
        if val:
            count += 1
        else:
            if 0 < count < min_consecutivos:
                for j in range(i-count, i):
                    mask[j] = False
            count = 0
    return mask

def detectar_episodios_no_mov(periodo_no_mov, total_amp, SR, timestamp_inicial, duracion_ventana=3):
    """
    Detecta episodios consecutivos de no movimiento (True en periodo_no_mov) y devuelve
    los tiempos como Timestamp reales y la amplitud media del episodio.
    
    Params:
        periodo_no_mov : lista o array de bool
        total_amp      : amplitud combinada de Yaw+Pitch+Roll
        SR             : frecuencia de muestreo (Hz)
        timestamp_inicial : primer timestamp del dataframe
        duracion_ventana : duración de cada ventana en segundos
    
    Returns:
        episodios_no_mov : lista de tuplas (inicio_ts, fin_ts, amp_med)
    """
    episodios_no_mov = []
    in_episode = False
    start_idx = 0

    for i, val in enumerate(periodo_no_mov):
        if val and not in_episode:
            in_episode = True
            start_idx = i
            
        elif not val and in_episode:
            in_episode = False
            fin_idx = i - 1

            inicio_s = start_idx * duracion_ventana
            fin_s = (fin_idx + 1) * duracion_ventana

            inicio_ts = timestamp_inicial + pd.to_timedelta(inicio_s, unit='s')
            fin_ts = timestamp_inicial + pd.to_timedelta(fin_s, unit='s')

            amp_segment = total_amp[int(inicio_s*SR):int(fin_s*SR)]
            amp_med = np.mean(amp_segment)

            episodios_no_mov.append((inicio_ts, fin_ts, amp_med))

    # Último episodio
    if in_episode:
        inicio_s = start_idx * duracion_ventana
        fin_s = len(periodo_no_mov) * duracion_ventana

        inicio_ts = timestamp_inicial + pd.to_timedelta(inicio_s, unit='s')
        fin_ts = timestamp_inicial + pd.to_timedelta(fin_s, unit='s')

        amp_segment = total_amp[int(inicio_s*SR):int(fin_s*SR)]
        amp_med = np.mean(amp_segment)

        episodios_no_mov.append((inicio_ts, fin_ts, amp_med))

    return episodios_no_mov

def graficar_temblor_coloreado(
    df, SR, temblores_yaw, temblores_pitch, temblores_roll,
    rms=None, episodios=None, anotaciones=None
):
    """
    Grafica Yaw, Pitch y Roll (y opcionalmente RMS) con fondo coloreado por detección de temblor.
    Abajo de todo agrega un subplot de anotaciones (intervalos de actividad) y marca con líneas
    verticales negras los límites entre actividades en todos los subplots superiores.
    """

    # --- preparación ---
    df = df.copy()
    
    base_date = datetime.datetime.today().date()  # Fecha base (puede ser cualquier día)

    # df['Timestamp']
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%H:%M:%S.%f')
    df['Timestamp'] = df['Timestamp'].apply(lambda x: x.replace(year=base_date.year,month=base_date.month,day=base_date.day))


    if not np.issubdtype(df['Timestamp'].dtype, np.datetime64):
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    ventana_muestras = int(3 * SR)
    n_rows = 3 + (1 if rms is not None else 0) + 1

    fig, axes = plt.subplots(
        n_rows, 1, figsize=(12, 8), sharex=True,
        gridspec_kw={'height_ratios': [0.1] + [1, 1, 1] + ([1] if rms is not None else []) }
    )

    # Normalizo manejo de ejes
    idx = 0
    ax_anno = axes[idx]; idx += 1
    ax_yaw = axes[idx]; idx += 1
    ax_pitch = axes[idx]; idx += 1
    ax_roll = axes[idx]; idx += 1
    ax_rms = None
    if rms is not None:
        ax_rms = axes[idx]; idx 
    

    # --- YAW ---
    ax_yaw.plot(df['Timestamp'], df['Yaw'], label='Yaw', color='r')
    ax_yaw.set_ylabel('Yaw (°)')
    ax_yaw.minorticks_on()
    ax_yaw.grid(which='major', linestyle='-', linewidth=0.7)
    ax_yaw.grid(which='minor', linestyle=':', linewidth=0.4)
    ax_yaw.legend()
    for i, (temblor, f, A) in enumerate(temblores_yaw):
        ini = df['Timestamp'].iloc[i * ventana_muestras]
        fin = df['Timestamp'].iloc[min((i + 1) * ventana_muestras - 1, len(df) - 1)]
        ax_yaw.axvspan(ini, fin, color='#ffcccc' if temblor else 'white', alpha=0.4, lw=0)

    # --- PITCH ---
    ax_pitch.plot(df['Timestamp'], df['Pitch'], label='Pitch', color='orange')
    ax_pitch.set_ylabel('Pitch (°)')
    ax_pitch.minorticks_on()
    ax_pitch.grid(which='major', linestyle='-', linewidth=0.7)
    ax_pitch.grid(which='minor', linestyle=':', linewidth=0.4)
    ax_pitch.legend()
    for i, (temblor, f, A) in enumerate(temblores_pitch):
        ini = df['Timestamp'].iloc[i * ventana_muestras]
        fin = df['Timestamp'].iloc[min((i + 1) * ventana_muestras - 1, len(df) - 1)]
        ax_pitch.axvspan(ini, fin, color='#ffcccc' if temblor else 'white', alpha=0.4, lw=0)

    # --- ROLL ---
    ax_roll.plot(df['Timestamp'], df['Roll'], label='Roll', color='green')
    ax_roll.set_ylabel('Roll (°)')
    ax_roll.minorticks_on()
    ax_roll.grid(which='major', linestyle='-', linewidth=0.7)
    ax_roll.grid(which='minor', linestyle=':', linewidth=0.4)
    ax_roll.legend()
    for i, (temblor, f, A) in enumerate(temblores_roll):
        ini = df['Timestamp'].iloc[i * ventana_muestras]
        fin = df['Timestamp'].iloc[min((i + 1) * ventana_muestras - 1, len(df) - 1)]
        ax_roll.axvspan(ini, fin, color='#ffcccc' if temblor else 'white', alpha=0.4, lw=0)

    # --- RMS (opcional) ---
    if rms is not None:
        ax_rms.plot(df['Timestamp'], rms, label='RMS Yaw+Pitch+Roll', color='b')
        ax_rms.set_ylabel('RMS (°)')
        ax_rms.minorticks_on()
        ax_rms.grid(which='major', linestyle='-', linewidth=0.7)
        ax_rms.grid(which='minor', linestyle=':', linewidth=0.4)
        ax_rms.legend()
        y_max = float(np.nanmax(rms)) if len(rms) else 1.0
        ax_rms.set_ylim(0, y_max * 1.1)
        if episodios is not None:
            for ini, fin, amp in episodios:
                ini, fin = pd.to_datetime(ini), pd.to_datetime(fin)
                ax_rms.axvspan(ini, fin, color='#ffcccc', alpha=0.35, lw=0)
                ax_rms.text(fin, y_max, f'Amp: {amp:.2f}', ha='right', va='top',
                            color="blue", fontsize=7, fontweight='bold',
                            bbox=dict(facecolor='white', edgecolor='none', pad=1.5))

    # --- Anotaciones ---
    ax_anno.set_ylim(0, 1)
    ax_anno.set_yticks([])
    ax_anno.grid(False)
    ax_anno.set_facecolor('white')

    activity_boundaries = []
    if anotaciones is not None and len(anotaciones) > 0:
        ann = anotaciones.copy()

        ann = anotaciones.copy()
        ann['inicio'] = pd.to_datetime(ann['inicio'], format='%H:%M:%S.%f')
        ann['inicio'] = ann['inicio'].apply(lambda x: x.replace(year=base_date.year,
                                                                month=base_date.month,
                                                                day=base_date.day))
        ann['fin'] = pd.to_datetime(ann['fin'], format='%H:%M:%S.%f')
        ann['fin'] = ann['fin'].apply(lambda x: x.replace(year=base_date.year,
                                                        month=base_date.month,
                                                        day=base_date.day))

        ann = ann.sort_values('inicio')
        for _, row in ann.iterrows():
            ini, fin = row['inicio'], row['fin']
            actividad = str(row.get('actividad', 'Actividad'))
            label = f"{actividad}" 
            ax_anno.axvspan(ini, fin, color='grey', alpha=0.5, lw=0)
            ax_anno.text(ini + (fin - ini)/2, 0.5, label, ha='center', va='center',
                         fontsize=8, color='black')
            activity_boundaries.append(ini)
            activity_boundaries.append(fin)
        # 🔹 ocultamos eje X en anotaciones
        ax_anno.set_xticks([])
        ax_anno.spines[['top', 'right', 'left', 'bottom']].set_visible(False)

    # --- Formato eje X ---
    all_axes = [ax_yaw, ax_pitch, ax_roll] + ([ax_rms] if ax_rms is not None else [])

    for ax in all_axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.tick_params(axis='x', rotation=0, labelbottom=True)

    # --- Líneas negras entre actividades ---
    if activity_boundaries:
        for ax in all_axes:
            for t in activity_boundaries:
                ax.axvline(pd.to_datetime(t), color='k', linewidth=0.8, alpha=0.9)

    plt.tight_layout()

    # ✅ Forzar etiquetas visibles en todos los ejes (menos anotaciones)
    for ax in all_axes:
        plt.setp(ax.get_xticklabels(), visible=True)

    # El último eje de datos con etiqueta del eje X
    last_data_ax = ax_rms if rms is not None else ax_roll

    plt.show()

def graficar_filtrados(df, df_filtered):   
        plt.figure(figsize=(10,8))

        plt.subplot(3,1,1)
        plt.plot(df['Timestamp'], df['Yaw'], label='Yaw Original', color='r', alpha=0.5)
        plt.plot(df_filtered['Timestamp'], df_filtered['Yaw'], label='Yaw Filtrado', color='r')
        plt.title('Yaw - Original vs Filtrado')
        plt.xlabel('Tiempo (s)')
        plt.ylabel('Yaw (grados)')
        plt.minorticks_on()  # activa los minor ticks
        plt.grid(which='major', linestyle='-', linewidth=0.7)
        plt.grid(which='minor', linestyle=':', linewidth=0.4)
        plt.legend()

        plt.subplot(3,1,2)
        plt.plot(df['Timestamp'], df['Pitch'], label='Pitch Original', color='orange', alpha=0.5)
        plt.plot(df_filtered['Timestamp'], df_filtered['Pitch'], label='Pitch Filtrado', color='orange')
        plt.title('Pitch - Original vs Filtrado')
        plt.xlabel('Tiempo (s)') 
        plt.ylabel('Pitch (grados)')
        plt.minorticks_on()
        plt.grid(which='major', linestyle='-', linewidth=0.7)
        plt.grid(which='minor', linestyle=':', linewidth=0.4)
        plt.legend()

        plt.subplot(3,1,3)
        plt.plot(df['Timestamp'], df['Roll'], label='Roll Original', color='green', alpha=0.5)
        plt.plot(df_filtered['Timestamp'], df_filtered['Roll'], label='Roll Filtrado', color='green')
        plt.title('Roll - Original vs Filtrado')
        plt.xlabel('Tiempo (s)')
        plt.ylabel('Roll (grados)')
        plt.minorticks_on()
        plt.grid(which='major', linestyle='-', linewidth=0.7)
        plt.grid(which='minor', linestyle=':', linewidth=0.4)
        plt.legend()
        
        plt.tight_layout()
        plt.show()

def detectar_temblor(df, SR, mostrar_pasos = False):
    # 1. Eliminaar deriva con filtro pasa altos iir
    yaw_filtered = pasa_altos_iir(df['Yaw'], SR)
    pitch_filtered = pasa_altos_iir(df['Pitch'], SR)
    roll_filtered = pasa_altos_iir(df['Roll'], SR)

    df_filtered = pd.DataFrame({
        'Timestamp': df['Timestamp'],
        'Yaw': yaw_filtered,
        'Pitch': pitch_filtered,
        'Roll': roll_filtered
    })

    if mostrar_pasos:
        graficar_filtrados(df, df_filtered)

    # 2. Ventaneo 
    window_size = 3 * SR  # 3 segundos
    overlap = 0
    yaw_windows = ventaneo(yaw_filtered, window_size, overlap)
    pitch_windows = ventaneo(pitch_filtered, window_size, overlap)
    roll_windows = ventaneo(roll_filtered, window_size, overlap)

    #3. Detección de temblor en cada ventana
    temblores_yaw = []
    temblores_pitch = []
    temblores_roll = []
    for i in range(yaw_windows.shape[0]):
        temblor_yaw, f_dom_yaw, amp_dom_yaw = metodo_burg_umbralizado(yaw_windows[i], SR)
        #print("Ciclo:", i+1) 
        #print("Yaw. Frecuencia dominante: ", f_dom_yaw, "Amplitud dominante: ", amp_dom_yaw, "Temblor: ", temblor_yaw)
        temblor_pitch, f_dom_pitch, amp_dom_pitch = metodo_burg_umbralizado(pitch_windows[i], SR)
        #print("Pitch. Frecuencia dominante: ", f_dom_pitch, "Amplitud dominante: ", amp_dom_pitch, "Temblor: ", temblor_pitch)

        temblor_roll, f_dom_roll, amp_dom_roll = metodo_burg_umbralizado(roll_windows[i], SR)
        #print("Roll. Frecuencia dominante: ", f_dom_roll, "Amplitud dominante: ", amp_dom_roll, "Temblor: ", temblor_roll)

        temblores_yaw.append((temblor_yaw, f_dom_yaw, amp_dom_yaw))
        temblores_pitch.append((temblor_pitch, f_dom_pitch, amp_dom_pitch))
        temblores_roll.append((temblor_roll, f_dom_roll, amp_dom_roll))

    # Mostrar resultados
    if mostrar_pasos:
        graficar_temblor_coloreado(df_filtered, SR, temblores_yaw, temblores_pitch, temblores_roll, rms = None, episodios=None)

    #4. Eliminar ventanas aisladas
    temblores_yaw_limpios = eliminar_ventanas_aisladas(temblores_yaw)
    temblores_pitch_limpios = eliminar_ventanas_aisladas(temblores_pitch)
    temblores_roll_limpios = eliminar_ventanas_aisladas(temblores_roll)
    if mostrar_pasos:
        graficar_temblor_coloreado(df_filtered, SR, temblores_yaw_limpios, temblores_pitch_limpios, temblores_roll_limpios, rms = None, episodios=None)

    # 5. Si un eje tiene temblor, los otros también
    temblores = []
    for i in range(len(temblores_yaw_limpios)):
        if temblores_yaw_limpios[i][0] or temblores_pitch_limpios[i][0] or temblores_roll_limpios[i][0]:
            temblores_yaw_limpios[i] = (True, temblores_yaw_limpios[i][1], temblores_yaw_limpios[i][2])
            temblores_pitch_limpios[i] = (True, temblores_pitch_limpios[i][1], temblores_pitch_limpios[i][2])
            temblores_roll_limpios[i] = (True, temblores_roll_limpios[i][1], temblores_roll_limpios[i][2])
            temblores.append(True)
        else:
            temblores.append(False)

    if mostrar_pasos:
        graficar_temblor_coloreado(df_filtered, SR, temblores_yaw_limpios, temblores_pitch_limpios, temblores_roll_limpios, rms = None, episodios=None)
    
    tiene_temblor = bool(np.any(temblores))

    return temblores, tiene_temblor, df_filtered, temblores_yaw_limpios, temblores_pitch_limpios, temblores_roll_limpios
 
def cuantificar_temblor(df, SR, temblores, graph=False):
    # 1. Pasa-bandas IIR 3.5–7.5 Hz
    yaw_band = pasa_bandas_iir(df['Yaw'], SR, 3.5, 7.5)
    pitch_band = pasa_bandas_iir(df['Pitch'], SR, 3.5, 7.5)
    roll_band = pasa_bandas_iir(df['Roll'], SR, 3.5, 7.5)

    # 2. Calcular RMS combinado
    rms_ypr = np.sqrt(yaw_band**2 + pitch_band**2 + roll_band**2)

    # 3. Detectar episodios de temblor y amplitud
    episodios = []
    in_episode = False
    start_idx = 0
    timestamp_inicial = df['Timestamp'].iloc[0]  # <-- referencia temporal

    duracion_ventana = 3  # segundos, igual que antes

    for i, t in enumerate(temblores):
        if t and not in_episode:
            in_episode = True
            start_idx = i

        elif not t and in_episode:
            in_episode = False
            fin_idx = i - 1

            inicio_s = start_idx * duracion_ventana
            fin_s = (fin_idx + 1) * duracion_ventana

            # Convertir segundos a Timestamps reales
            inicio_ts = timestamp_inicial + pd.to_timedelta(inicio_s, unit='s')
            fin_ts = timestamp_inicial + pd.to_timedelta(fin_s, unit='s')

            rms_segment = rms_ypr[int(inicio_s * SR):int(fin_s * SR)]
            amp_episode = np.max(rms_segment)
            episodios.append((inicio_ts, fin_ts, amp_episode))

    # Último episodio
    if in_episode:
        fin_idx = len(temblores) - 1
        inicio_s = start_idx * duracion_ventana
        fin_s = (fin_idx + 1) * duracion_ventana

        inicio_ts = timestamp_inicial + pd.to_timedelta(inicio_s, unit='s')
        fin_ts = timestamp_inicial + pd.to_timedelta(fin_s, unit='s')

        rms_segment = rms_ypr[int(inicio_s * SR):int(fin_s * SR)]
        amp_episode = np.max(rms_segment)
        episodios.append((inicio_ts, fin_ts, amp_episode))

    # 4. Graficar
    if graph:
        plt.figure(figsize=(10, 5))
        plt.plot(df['Timestamp'], rms_ypr, label='RMS Yaw+Pitch+Roll', color='b')
        plt.title('RMS combinado de Yaw, Pitch y Roll')
        plt.xlabel('Tiempo')
        plt.ylabel('RMS (°)')
        plt.minorticks_on()
        plt.grid(which='major', linestyle='-', linewidth=0.7)
        plt.grid(which='minor', linestyle=':', linewidth=0.4)

        y_max = np.max(rms_ypr) * 1.1
        plt.ylim(0, y_max * 1.1)

        for inicio_ts, fin_ts, amp in episodios:
            plt.axvspan(inicio_ts, fin_ts, color='lightgreen', alpha=0.4, lw=0)
            plt.text(fin_ts, y_max * 0.95, f'{amp:.2f}', ha='right', va='top',
                     color='green', fontsize=10, fontweight='bold')

        plt.legend()
        plt.tight_layout()
        plt.show()

    return rms_ypr, episodios

def frecuencia_temblor(df, episodios, SR):
    
    # Pasa altos para eliminar deriva
    df = df.copy()
    df['Yaw'] = pasa_altos_iir(df['Yaw'], SR, fc=0.5)
    df['Pitch'] = pasa_altos_iir(df['Pitch'], SR, fc=0.5)
    df['Roll'] = pasa_altos_iir(df['Roll'], SR, fc=0.5)

    # --- CASO 1: NO HAY EPISODIOS DE TEMBLOR DETECTADOS ---
    if not episodios:
        # En lugar de devolver vacío, analizamos la señal completa
        # Promediamos los 3 ejes para tener una señal unificada
        segmento_completo = (df['Yaw'] + df['Pitch'] + df['Roll']) / 3
        
        # Calculamos Burg sobre toda la señal
        order = 6
        try:
            burg = pburg(segmento_completo, order=order)
            psd_mean = np.asarray(burg.psd)
            freqs_std = np.linspace(0, SR/2, len(psd_mean))
            
            # Frecuencia dominante global
            idx_max = np.argmax(psd_mean)
            f_dom_mean = freqs_std[idx_max]
            
            # Devolvemos:
            # - Lista de frecuencias por episodio: vacía (porque no hay episodios)
            # - f_dom_mean: la del análisis global
            # - freqs_std y psd_mean: datos para graficar el espectro completo
            return [], f_dom_mean, freqs_std, psd_mean
            
        except Exception as e:
            # Si falla Burg por señal muy corta o plana, devolvemos arrays vacíos seguros
            print(f"Error en Burg fallback: {e}")
            return [], 0.0, np.array([]), np.array([])

    # --- CASO 2: SÍ HAY EPISODIOS (Lógica original) ---
    # Lista para guardar todas las PSD
    todas_psd = []
    frecuencias = []

    for (inicio_ts, fin_ts, amp) in episodios:

        # Convertir timestamps a índices
        inicio_idx = df.index[df['Timestamp'] >= inicio_ts][0]
        fin_idx = df.index[df['Timestamp'] <= fin_ts][-1]

        # Extraer segmento promediado
        segmento = (
            df['Yaw'].iloc[inicio_idx:fin_idx+1]
            + df['Pitch'].iloc[inicio_idx:fin_idx+1]
            + df['Roll'].iloc[inicio_idx:fin_idx+1]
        ) / 3

        # Burg
        order = 6
        burg = pburg(segmento, order=order)
        psd = np.asarray(burg.psd)
        freqs = np.linspace(0, SR/2, len(psd))

        # Guardamos para promediarlas más tarde
        todas_psd.append(psd)

        # Frecuencia dominante de este episodio
        idx_max = np.argmax(psd)
        f_dom = freqs[idx_max]
        frecuencias.append(f_dom)

    # ============================
    #   PROMEDIO DEL ESPECTRO
    # ============================

    # Interpolar todas las PSD al mismo eje de frecuencias
    n_fft_std = min(len(psd) for psd in todas_psd)
    freqs_std = np.linspace(0, SR/2, n_fft_std)

    psd_interp = []
    for psd in todas_psd:
        freqs_original = np.linspace(0, SR/2, len(psd))
        psd_interp.append(np.interp(freqs_std, freqs_original, psd))

    # Promedio final
    psd_mean = np.mean(psd_interp, axis=0)

    # Frecuencia dominante global
    idx_max = np.argmax(psd_mean)
    f_dom_mean = freqs_std[idx_max]

    return frecuencias, f_dom_mean, freqs_std, psd_mean