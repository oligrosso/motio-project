import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import scipy.signal as signal
from scipy.signal import butter, filtfilt, hilbert
from spectrum import pburg
import matplotlib.dates as mdates
import datetime as datetime
import datetime
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay, accuracy_score, precision_score, recall_score, f1_score
import os

def cargar_datos(path):
    # Leer archivo
    df = pd.read_csv(path, sep=",", encoding="latin1", on_bad_lines="skip")
    df = df.iloc[:-1]
    df.columns = df.columns.str.strip()  # limpiar nombres

    # Convertir la columna 'Timestamp' a formato datetime
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

    return  df, SR

def graficar_datos(df):
    #Graficar los datos de yaw, pitch y roll
    plt.figure(figsize=(10,8))

    plt.subplot(3,1,1)
    plt.plot(df['Timestamp'], df['Yaw'], label='Yaw', color='r')
    plt.title('Yaw')
    plt.xlabel('Tiempo (s)')
    plt.ylabel('Yaw (grados)')
    plt.minorticks_on()  # activa los minor ticks
    plt.grid(which='major', linestyle='-', linewidth=0.7)
    plt.grid(which='minor', linestyle=':', linewidth=0.4)

    plt.subplot(3,1,2)
    plt.plot(df['Timestamp'], df['Pitch'], label='Pitch', color='orange')
    plt.title('Pitch')
    plt.xlabel('Tiempo (s)') 
    plt.ylabel('Pitch (grados)')
    plt.minorticks_on()
    plt.grid(which='major', linestyle='-', linewidth=0.7)
    plt.grid(which='minor', linestyle=':', linewidth=0.4)

    plt.subplot(3,1,3)
    plt.plot(df['Timestamp'], df['Roll'], label='Roll', color='green')
    plt.title('Roll')
    plt.xlabel('Tiempo (s)')
    plt.ylabel('Roll (grados)')
    plt.minorticks_on()
    plt.grid(which='major', linestyle='-', linewidth=0.7)
    plt.grid(which='minor', linestyle=':', linewidth=0.4)
    
    plt.tight_layout()
    plt.show()

def graficar_fourier(df):
    # Graficar la Transformada de Fourier de yaw, pitch y roll
    N = len(df)
    T = 1.0 / SR
    yf_yaw = np.fft.fft(df['Yaw'])
    yf_pitch = np.fft.fft(df['Pitch'])
    yf_roll = np.fft.fft(df['Roll'])
    xf = np.fft.fftfreq(N, T)[:N//2]

    plt.figure(figsize=(10,8))
    plt.subplot(3,1,1)
    plt.plot(xf, 2.0/N * np.abs(yf_yaw[0:N//2]), color='r')
    plt.title('FFT Yaw')
    plt.xlabel('Frecuencia (Hz)')
    plt.ylabel('Amplitud')
    plt.grid()
    plt.minorticks_on()
    plt.grid(which='major', linestyle='-', linewidth=0.7)
    plt.grid(which='minor', linestyle=':', linewidth=0.4)
    plt.xlim(0, 20)
    
    plt.subplot(3,1,2)
    plt.plot(xf, 2.0/N * np.abs(yf_pitch[0:N//2]), color='orange')
    plt.title('FFT Pitch')
    plt.xlabel('Frecuencia (Hz)')
    plt.ylabel('Amplitud')
    plt.grid()
    plt.minorticks_on()
    plt.grid(which='major', linestyle='-', linewidth=0.7)
    plt.grid(which='minor', linestyle=':', linewidth=0.4)
    plt.xlim(0, 20)
    
    plt.subplot(3,1,3)
    plt.plot(xf, 2.0/N * np.abs(yf_roll[0:N//2]), color='green')
    plt.title('FFT Roll')
    plt.xlabel('Frecuencia (Hz)')
    plt.ylabel('Amplitud')
    plt.grid()
    plt.minorticks_on()
    plt.grid(which='major', linestyle='-', linewidth=0.7)
    plt.grid(which='minor', linestyle=':', linewidth=0.4)
    plt.xlim(0, 20)
    
    plt.tight_layout()
    plt.show()

    return

def pasa_altos_iir(signal, SR, fc =0.25):
    # Diseño del filtro pasa altos
    fs = SR  # Frecuencia de muestreo
    w = fc / (fs / 2)  # Frecuencia normalizada
    b, a = butter(1, w, btype='high')

    # Aplicar el filtro a la señal
    filtered_signal = filtfilt(b, a, signal)
    
    return filtered_signal

def pasa_bajos_iir(signal, SR, fc = 3.5):
    # Diseño del filtro pasa bajos
    fs = SR  # Frecuencia de muestreo
    w = fc / (fs / 2)  # Frecuencia normalizada
    b, a = butter(8, w, btype='low')

    # Aplicar el filtro a la señal
    filtered_signal = filtfilt(b, a, signal)
    
    return filtered_signal

def pasa_bandas_iir(signal, SR, flow, fhigh):
    # Diseño del filtro pasa bandas
    fs = SR  # Frecuencia de muestreo
    lowcut = flow  # Frecuencia de corte baja
    highcut = fhigh # Frecuencia de corte alta
    w1 = lowcut / (fs / 2)  # Frecuencia normalizada
    w2 = highcut / (fs / 2)  # Frecuencia normalizada
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

def metodo_burg_polos(window):
    order = 6 # Orden del modelo AR
    burg = pburg(window, order=order)

    # Coeficientes AR (con signo invertido según convención)
    burg()
    ar_coeffs = np.r_[1, -burg.ar]   # agrega el 1 y cambia el signo

    # Calcular polos del modelo AR
    polos = np.roots(ar_coeffs)
    polos_complejos = polos[np.imag(polos) > 1e-2]  # solo polos complejos

    # Calcular frecuencia y amplitud de todos los polos complejos
    frecs = np.angle(polos_complejos) / (2*np.pi) * SR
    amps  = np.abs(polos_complejos)

    mask = (amps > 0.1) & (amps < 1.0)
    frecs = frecs[mask]
    amps  = amps[mask]

    # Elegir el “polo dominante” como el de mayor amplitud en ese rango
    idx_dom = np.argmax(amps)
    f_dom = frecs[idx_dom]
    amp_dom = amps[idx_dom]

    #print("Polo dominante:", polo_dominante)

    # Detección de temblor
    temblor = False
    if 3.5 < f_dom < 7.5 and amp_dom > 0.5:
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

    return temblores, df_filtered, temblores_yaw_limpios, temblores_pitch_limpios, temblores_roll_limpios

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


def detectar_bradicinesia(df, SR, graph=False):
    # 1. Eliminar deriva con filtro pasa altos iir
    yaw_filtered = pasa_altos_iir(df['Yaw'], SR)
    pitch_filtered = pasa_altos_iir(df['Pitch'], SR)
    roll_filtered = pasa_altos_iir(df['Roll'], SR)

    # 2. Eliminar alta frecuencia con filtro pasa bajos iir
    yaw_filtered = pasa_bajos_iir(yaw_filtered, SR)
    pitch_filtered = pasa_bajos_iir(pitch_filtered, SR)
    roll_filtered = pasa_bajos_iir(roll_filtered, SR)

    # 3. Crear DataFrame filtrado
    df_bradicinesia = pd.DataFrame({
        'Timestamp': df['Timestamp'],
        'Yaw': yaw_filtered,
        'Pitch': pitch_filtered,
        'Roll': roll_filtered
    })

    # 4. Calcular amplitud combinada (Hilbert)
    yaw_hilbert = np.abs(hilbert(yaw_filtered))
    pitch_hilbert = np.abs(hilbert(pitch_filtered))
    roll_hilbert = np.abs(hilbert(roll_filtered))

    total_amp = np.sqrt(yaw_hilbert**2 + pitch_hilbert**2 + roll_hilbert**2)

    # 5. Ventaneo de amplitud
    window_size = 3 * SR  # 3 segundos
    overlap = 0
    total_amp_windows = ventaneo(total_amp, window_size, overlap)
    avg_total_amp = np.array([np.mean(window) for window in total_amp_windows])

    # 6. Detección de no movimiento
    umbral_movimiento = 5
    periodo_no_mov = [amp < umbral_movimiento for amp in avg_total_amp]

    # Limpieza de ventanas aisladas
    periodo_no_mov_limpio = eliminar_ventanas_aisladas_bool(periodo_no_mov)

    # 7. Detectar episodios de no movimiento (timestamps)
    episodios_no_mov = detectar_episodios_no_mov(
        periodo_no_mov_limpio, total_amp, SR,
        df['Timestamp'].iloc[0], duracion_ventana=3
    )

    # 8. Cuantificar bradicinesia
    episodios_finales = cuantificar_bradicinesia(df_bradicinesia, episodios_no_mov)

    # 9. Gráfico opcional
    if graph:
        plt.figure(figsize=(10, 5))
        plt.plot(df['Timestamp'], total_amp, label='Amplitud combinada', color='b')
        plt.title('Amplitud combinada de Yaw, Pitch y Roll')
        plt.xlabel('Tiempo')
        plt.ylabel('Amplitud (°)')
        plt.minorticks_on()
        plt.grid(which='major', linestyle='-', linewidth=0.7)
        plt.grid(which='minor', linestyle=':', linewidth=0.4)

        y_max = np.max(total_amp) * 1.1
        plt.ylim(0, y_max)

        for i, (inicio, fin, amp) in enumerate(episodios_no_mov):
            # inicio y fin ahora son Timestamps, axvspan los acepta directamente
            plt.axvspan(inicio, fin, color='lightcoral', alpha=0.4, lw=0)

            # Textos (ubicados un poco desplazados en tiempo si querés que no se superpongan)
            plt.text(fin, y_max * 0.95, f'{amp:.2f}',
                     ha='right', va='top', color='red', fontsize=10, fontweight='bold')

            # Si episodios_finales[i] tiene métricas, asegurate que existan esos índices
            if len(episodios_finales[i]) >= 5:
                plt.text(inicio, y_max * 0.9, f'Mh={episodios_finales[i][3]:.2f}',
                         ha='left', va='top', color='red', fontsize=9, fontweight='bold')
                plt.text(inicio, y_max * 0.8, f'Rh={episodios_finales[i][4]:.2f}',
                         ha='left', va='top', color='red', fontsize=9, fontweight='bold')

        plt.legend()
        plt.tight_layout()
        plt.show()

    return df_bradicinesia, episodios_no_mov

def cuantificar_bradicinesia(df, episodios):
    # --- 1. Calcular duraciones de episodios ---
    duraciones = [fin - inicio for inicio, fin, amp_med in episodios]
    dt = np.mean(np.diff(df['Timestamp']).astype('timedelta64[s]'))  # segundos por muestra
    if isinstance(dt, np.timedelta64):
        dt = dt / np.timedelta64(1, 's')
    elif hasattr(dt, 'total_seconds'):
        dt = dt.total_seconds()

    # --- 2. Movilidad de la mano ---
    movilidad = np.sqrt(df['Yaw']**2 + df['Pitch']**2 + df['Roll']**2)

    episodios_mov = []
    for inicio, fin, amp_med in episodios:
        movilidad_segment = movilidad[(df['Timestamp'] >= inicio) & (df['Timestamp'] <= fin)]
        movilidad_media = np.mean(movilidad_segment)
        episodios_mov.append((inicio, fin, amp_med, movilidad_media))

    # --- 3. Actividad de la mano ---
    duracion_total = df['Timestamp'].iloc[-1] - df['Timestamp'].iloc[0]
    tiempo_no_mov = sum([d.total_seconds() for d in duraciones])
    tiempo_mov = duracion_total.total_seconds() - tiempo_no_mov
    actividad = tiempo_mov / duracion_total.total_seconds() if duracion_total.total_seconds() > 0 else 0

    # --- 4. Asegurar tipos numéricos ---
    for col in ["Yaw", "Pitch", "Roll"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- 5. Calcular ángulos acumulados ---
    angle_yaw = np.cumsum(df["Yaw"].to_numpy(dtype=float) * dt)
    angle_pitch = np.cumsum(df["Pitch"].to_numpy(dtype=float) * dt)
    angle_roll = np.cumsum(df["Roll"].to_numpy(dtype=float) * dt)

    # --- 6. Rango de rotación por episodio ---
    episodios_finales = []
    for inicio, fin, amp_med, movilidad_media in episodios_mov:
        mask = (df['Timestamp'] >= inicio) & (df['Timestamp'] <= fin)

        # Si no hay datos en el rango, saltar el episodio
        if not mask.any():
            print(f"[ADVERTENCIA] Episodio sin datos entre {inicio} y {fin}")
            continue

        angle_yaw_seg = angle_yaw[mask.to_numpy()]
        angle_pitch_seg = angle_pitch[mask.to_numpy()]
        angle_roll_seg = angle_roll[mask.to_numpy()]

        if len(angle_yaw_seg) == 0:
            print(f"[ADVERTENCIA] Segmento vacío entre {inicio} y {fin}")
            continue

        # Cálculo de rangos seguros (todo numérico)
        rango_yaw_seg = float(np.max(angle_yaw_seg) - np.min(angle_yaw_seg))
        rango_pitch_seg = float(np.max(angle_pitch_seg) - np.min(angle_pitch_seg))
        rango_roll_seg = float(np.max(angle_roll_seg) - np.min(angle_roll_seg))

        rango_combinado = np.sqrt(
            rango_yaw_seg**2 + rango_pitch_seg**2 + rango_roll_seg**2
        )

        episodios_finales.append((inicio, fin, amp_med, movilidad_media, rango_combinado))

    return episodios_finales


def graficar_frecuencia_amplitud(df, SR):
    yaw = df['Yaw']
    pitch = df['Pitch']
    roll = df['Roll']

    # Filtrar entre 2 y 8 Hz
    yaw_band = pasa_bandas_iir(yaw, SR, 2.5, 9.5)
    pitch_band = pasa_bandas_iir(pitch, SR, 2.5, 9.5)
    roll_band = pasa_bandas_iir(roll, SR, 2.5, 9.5)

    # Promedio de mediciones
    promedio = (yaw_band + pitch_band + roll_band) / 3

    # FFT
    N = len(promedio)
    T = 1.0 / SR
    yf = np.fft.fft(promedio)
    xf = np.fft.fftfreq(N, T)[:N//2]
    yf_magnitude = 2.0 / N * np.abs(yf[0:N//2])

    #yf_magnitude = smooth(yf_magnitude, window_size=5)

    # Frecuencia dominante
    freq_dom = xf[np.argmax(yf_magnitude)]
    amp_dom = yf_magnitude[np.argmax(yf_magnitude)]

    # Graficar espectro
    plt.figure(figsize=(10, 5))
    plt.plot(xf, yf_magnitude, color='b')
    plt.axvline(freq_dom, color='r', linestyle='--', label=f'Frecuencia dominante')
    plt.scatter(freq_dom, amp_dom, color='r')  # Marca el pico
    plt.text(freq_dom + 0.1, amp_dom, f'{freq_dom:.1f} Hz', color='r', fontsize=12)
    plt.title('Espectro de Frecuencia - Promedio lineal (Yaw + Pitch + Roll)')
    plt.xlabel('Frecuencia (Hz)')
    plt.ylabel('Amplitud')
    plt.xlim(3, 10)  # <-- este rango se aplicará
    plt.minorticks_on()
    plt.grid(which='major', linestyle='-', linewidth=0.7)
    plt.grid(which='minor', linestyle=':', linewidth=0.4)
    plt.legend()
    plt.tight_layout()
    plt.show()


def evaluar_deteccion_temblor(df, anotaciones, SR):
    condiciones_temblor = ["Reposo", "Postural", "NarizReposo", "postural", "reposo"]

    # Ventaneo
    duracion_ventana = 3  # segundos
    muestras_ventana = duracion_ventana * SR
    ventanas = ventaneo(df['Timestamp'], muestras_ventana, 0)

    # Corregir fechas
    fecha_ref = pd.to_datetime(df['Timestamp'].iloc[0]).date()
    anotaciones['inicio'] = pd.to_datetime(anotaciones['inicio'], format='%H:%M:%S.%f', errors='coerce').apply(
        lambda t: pd.Timestamp.combine(fecha_ref, t.time()) if pd.notnull(t) else t
    )
    anotaciones['fin'] = pd.to_datetime(anotaciones['fin'], format='%H:%M:%S.%f', errors='coerce').apply(
        lambda t: pd.Timestamp.combine(fecha_ref, t.time()) if pd.notnull(t) else t
    )

    # Etiquetas verdaderas
    y_true = []
    for ventana in ventanas:
        inicio_ts = ventana[0]
        fin_ts = ventana[-1]

        temblor_en_ventana = False
        for _, row in anotaciones.iterrows():
            inicio_anno = pd.to_datetime(row['inicio'], format='%H:%M:%S.%f')
            fin_anno = pd.to_datetime(row['fin'], format='%H:%M:%S.%f')
            actividad = str(row.get('actividad', '')).strip()
            grado = row.get('grado', 0)

            centro_ventana = inicio_ts + (fin_ts - inicio_ts) / 2
            if inicio_anno <= centro_ventana <= fin_anno:
                if actividad in condiciones_temblor and pd.notnull(grado) and grado > 0:
                    temblor_en_ventana = True
                break
        y_true.append(temblor_en_ventana)

    # Predicciones
    temblores, df_filt, yaw, pitch, roll = detectar_temblor(df, SR, mostrar_pasos=False)
    y_pred = np.array(temblores, dtype=int)

    # Igualar longitudes
    min_len = min(len(y_true), len(y_pred))
    return y_true[:min_len], y_pred[:min_len]


def graficar_matriz_confusion(y_true, y_pred, titulo="Matriz de Confusión"):
    # Calcular matriz de confusión
    cm = confusion_matrix(y_true, y_pred)

    # Calcular métricas
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    # Crear figura con dos subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4))

    # Matriz de confusión
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=["Sin temblor", "Con temblor"])
    disp.plot(cmap="Blues", values_format="d", colorbar=False, ax=ax1)
    ax1.set_title(titulo)
    ax1.set_xlabel("Predicción")
    ax1.set_ylabel("Verdadero")
    ax1.grid(False)

    # Subplot con métricas
    ax2.axis("off")
    metrics_text = (
        f"Métricas del modelo\n\n"
        f"Accuracy:  {acc:.3f}\n"
        f"Precision: {prec:.3f}\n"
        f"Recall:    {rec:.3f}\n"
        f"F1-score:  {f1:.3f}"
    )
    ax2.text(0.05, 0.7, metrics_text, fontsize=12, va="top", family="monospace")

    plt.tight_layout()
    plt.show()



def frecuencia_temblor(df, episodios, SR):
    if not episodios:
        return
    
    # Pasa altos para eliminar deriva
    df = df.copy()
    df['Yaw'] = pasa_altos_iir(df['Yaw'], SR, fc=0.5)
    df['Pitch'] = pasa_altos_iir(df['Pitch'], SR, fc=0.5)
    df['Roll'] = pasa_altos_iir(df['Roll'], SR, fc=0.5)

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

    # ============================
    #   GRAFICAR PROMEDIO
    # ============================

    plt.figure(figsize=(7, 4))
    plt.plot(freqs_std, psd_mean, label='PSD promedio')
    plt.axvline(f_dom_mean, color='r', linestyle='--', label=f'F. dominante promedio: {f_dom_mean:.2f} Hz')
    plt.scatter([f_dom_mean], [psd_mean[idx_max]], color='r')
    plt.xlabel("Frecuencia (Hz)")
    plt.ylabel("PSD")
    plt.xlim(0, min(15, SR/2))
    plt.title("Espectro PROMEDIO de episodios de temblor")
    plt.legend()
    plt.tight_layout()
    plt.show()

    return frecuencias, f_dom_mean


# --- MAIN ---
BASE_DIR = "/Users/gross/Interfaz-Guante-PD"
PACIENTE = "Paciente1"   # CAMBIAR

# === Rutas automáticas ===
path_datos = os.path.join(BASE_DIR, f"{PACIENTE}.csv")
path_notas = os.path.join(BASE_DIR, f"Notas_{PACIENTE}.csv")

# === Cargar anotaciones ===
if os.path.exists(path_notas):
    anotaciones = pd.read_csv(path_notas)
else:
    print(f"⚠️ No se encontró archivo de notas para {PACIENTE}.")
    anotaciones = None

# === Cargar datos principales ===
df, SR = cargar_datos(path_datos)
print(f"Frecuencia de muestreo (SR): {SR} Hz")

# === Procesamiento ===
temblores, df_filt, yaw, pitch, roll = detectar_temblor(df, SR, mostrar_pasos=True)
print(temblores)
tiene_temblor = bool(np.any(temblores))
print("Tiene temblor", tiene_temblor)
rms_ypr, episodios = cuantificar_temblor(df, SR, temblores, graph=True)

# === GRAFICO 1 AMPLITUD VS TIEMPO & EVENTOS DE TEMBLOR CON ACTIVIDADES===
graficar_temblor_coloreado(df_filt, SR, yaw, pitch, roll,rms_ypr, episodios,anotaciones=anotaciones)

#detectar_bradicinesia(df, SR, graph=True)

# === GRAFICO 2 AMPLITUD VS FRECUENCIA ===
graficar_frecuencia_amplitud(df, SR)

# === GRAFICO 3 PSD VS FRECUENCIA===
frecuencia_temblor(df, episodios, SR)


y_true, y_pred = evaluar_deteccion_temblor(df, anotaciones, SR)
#graficar_matriz_confusion(y_true, y_pred, titulo=f"Matriz de Confusión - Detección de Temblor ({PACIENTE})")

# === EVALUACION GLOBAL ===
Y_TRUE_GLOBAL = []
Y_PRED_GLOBAL = []

for i in range(1, 6):
    PACIENTE = f"Paciente{i}"
    print(f"\n=== Procesando {PACIENTE} ===")

    path_datos = os.path.join(BASE_DIR, f"{PACIENTE}.csv")
    path_notas = os.path.join(BASE_DIR, f"Notas_{PACIENTE}.csv")

    if not (os.path.exists(path_datos) and os.path.exists(path_notas)):
        print(f"⚠️ Faltan datos o notas para {PACIENTE}, se salta.")
        continue

    df, SR = cargar_datos(path_datos)
    anotaciones = pd.read_csv(path_notas)

    y_true, y_pred = evaluar_deteccion_temblor(df, anotaciones, SR)

    Y_TRUE_GLOBAL.extend(y_true)
    Y_PRED_GLOBAL.extend(y_pred)


#graficar_matriz_confusion(Y_TRUE_GLOBAL, Y_PRED_GLOBAL, titulo="Matriz de Confusión - Detección de Temblor (Global)")