# Código para leer los datos transmitidos por el wifi del microcontrolador
import socket # Sirve para recibir datos por red (UDP) desde el ESP8266.
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque # deque es como una lista “cinta transportadora”: cuando se llena, tira lo más viejo y agrega lo nuevo.
import csv
from datetime import datetime # Para tener la hora actual y poner timestamps.
from matplotlib.widgets import Button, TextBox
import tkinter as tk
from tkinter import simpledialog

# --- VENTANA TKINTER PARA NOMBRE DE ARCHIVO ---
root = tk.Tk()
root.withdraw()  # Oculta la ventana principal
filename = simpledialog.askstring("Nombre de archivo", "Ingrese el nombre del archivo:")
if not filename:
    filename = "mpu_data"  # nombre por defecto

# --- CONFIGURACIÓN UDP ---
UDP_IP = "0.0.0.0" # Significa: “escuchá en todas las interfaces de red de mi PC”.
UDP_PORT = 4210 # Puerto donde va a escuchar (tu ESP debería mandar a ese puerto).
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # Crea un socket UDP (SOCK_DGRAM = UDP).
sock.bind((UDP_IP, UDP_PORT)) # Se “engancha” (bind) a esa IP/puerto para recibir datos.
sock.setblocking(False) # Muy importante: hace que recvfrom() no trabe el programa esperando datos. Si no hay datos, tira error BlockingIOError y seguimos.

# --- CSV DE DATOS ---
csv_path = f"/Users/gross/Interfaz-Guante-PD/{filename}.csv" # Arma el path final del archivo usando el nombre que pusiste.
data_csv = open(csv_path, "w", newline="") # Abre el CSV en modo escritura (w).
data_writer = csv.writer(data_csv) # Crea el “escritor” para poder hacer writerow() fácil.
data_writer.writerow(["Timestamp", "Yaw", "Pitch", "Roll", "Ax", "Ay", "Az"]) # Escribe la primera fila (los nombres de columnas).

# --- CSV DE ACTIVIDADES ---
act_csv_path = f"/Users/gross/Interfaz-Guante-PD/Notas_{filename}.csv"
act_csv = open(act_csv_path, "w", newline="")
act_writer = csv.writer(act_csv)
act_writer.writerow(["inicio", "fin", "actividad"]) # ENCABEZADO

# --- VARIABLES DE ANIMACIÓN ---
max_len = 50 # Cantidad de puntos que vas a mostrar en pantalla (últimos 50).
# Tres “colas” que guardan los últimos 50 valores de yaw/pitch/roll. Arrancan llenas de ceros.
yaw_data = deque([0]*max_len, maxlen=max_len) 
pitch_data = deque([0]*max_len, maxlen=max_len)
roll_data = deque([0]*max_len, maxlen=max_len)

fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.2)  # espacio para botones y textbox abajo
# Crea 3 líneas vacías (se van a llenar después con datos):
line_yaw, = ax.plot([], [], label='Yaw', color='r')
line_pitch, = ax.plot([], [], label='Pitch', color='g')
line_roll, = ax.plot([], [], label='Roll', color='b') # El , es porque plot() devuelve una lista de líneas y vos querés solo 1.
ax.set_ylim(-180, 180) # Rango vertical: grados.
ax.set_xlim(0, max_len) # Rango horizontal: 0 a 50 puntos.
ax.set_xlabel('Tiempo')
ax.set_ylabel('Grados')
ax.legend()
ax.grid(True)

# --- ACTIVIDAD ACTUAL ---
actividad_actual = None # No hay actividad iniciada todavía.
inicio_actual = None

def nueva_actividad(event): # Función que se ejecuta cuando apretás Enter o el botón “Registrar”.
    global actividad_actual, inicio_actual # Dice: “voy a modificar las variables globales”.
    texto = text_box.text.strip() # Agarra lo que escribiste en el textbox y le saca espacios.
    if not texto:
        return
    ahora = datetime.now() # Guarda la hora actual.
    # Si ya había una actividad activa, la cierra
    if actividad_actual is not None:
        act_writer.writerow([
            inicio_actual.strftime("%H:%M:%S.%f")[:-3], # [:-3] corta microsegundos para dejar milisegundos.
            ahora.strftime("%H:%M:%S.%f")[:-3],
            actividad_actual
        ])
        act_csv.flush() # Fuerza a que se escriba en disco ya (por si se cuelga algo).
        print(f"Actividad registrada: {actividad_actual} {inicio_actual} - {ahora}") # Muestra por consola lo que se registró.
    # Iniciar nueva actividad
    actividad_actual = texto
    inicio_actual = ahora
    text_box.set_val("")  # limpiar textbox

# --- BOTON Y TEXTBOX ---
# Crea la cajita de texto en la parte inferior:
axbox = plt.axes([0.1, 0.05, 0.5, 0.05])
text_box = TextBox(axbox, "Nueva actividad")

# Enlazamos la función al evento "submit" (Enter)
text_box.on_submit(nueva_actividad) # Si apretás Enter, llama a nueva_actividad.

# --- Boton registrar como opcion en vez de enter ---
axbtn = plt.axes([0.65, 0.05, 0.2, 0.05])
btn = Button(axbtn, "Registrar")
btn.on_clicked(lambda event: nueva_actividad(None))  # Cuando clickeás el botón, llama a la misma función (como si fuera Enter).

# --- FUNCION DE ANIMACIÓN ---
def update(frame): # Esta función la llama Matplotlib todo el tiempo para actualizar el gráfico.
    last_data = None # Variable para quedarte con el último paquete UDP (yaw,pitch,roll,ax,ay,az) recibido.
    while True: # lee TODOS los paquetes que llegaron desde la última vez, y se queda solo con el más reciente e ignora los viejos.
        try:
            data, addr = sock.recvfrom(1024) # data → el contenido del paquete (bytes); addr → quién lo mandó (IP y puerto); 1024 → tamaño máximo del mensaje
            last_data = data
        except BlockingIOError: # Si no hay más datos, corta el loop.
            break

    if last_data is not None: # si llegó algo
        try:
            values = [float(x) for x in last_data.decode('utf-8').strip().split(',')[1:]] # lo convierte de bytes a texto, lo separa por comas, lo pasa a float y asigna a variables.
            yaw, pitch, roll, ax_val, ay_val, az_val = values
            # Mete los valores nuevos en las colas (y si hay más de 50, se cae el más viejo).
            yaw_data.append(yaw)
            pitch_data.append(pitch)
            roll_data.append(roll)
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3] # Hora actual con milisegundos.
            data_writer.writerow([timestamp, yaw, pitch, roll, ax_val, ay_val, az_val]) # Guarda una fila en el CSV de datos.
        except ValueError: # Si el paquete vino mal formateado, lo ignora.
            pass

    line_yaw.set_data(range(len(yaw_data)), yaw_data) # Eje X: 0..49, Eje Y: valores de yaw
    line_pitch.set_data(range(len(pitch_data)), pitch_data)
    line_roll.set_data(range(len(roll_data)), roll_data)
    return line_yaw, line_pitch, line_roll # Devuelve las líneas para que Matplotlib las repinte.

# --- ANIMACION ---
ani = animation.FuncAnimation(fig, update, interval=5, blit=False) # Cada 20 ms llama a update(). blit=False repinta todo (más simple, menos optimización).
plt.show() # Abre la ventana del gráfico y queda corriendo hasta que la cierres.

# --- AL CERRAR ---
data_csv.close() # Cierra el CSV principal.
# cerrar última actividad si existe
if actividad_actual is not None: # Si había una actividad activa, la cierra automáticamente al momento de salir.
    ahora = datetime.now()
    act_writer.writerow([
        inicio_actual.strftime("%H:%M:%S.%f")[:-3],
        ahora.strftime("%H:%M:%S.%f")[:-3],
        actividad_actual
    ])
act_csv.close() # Cierra el CSV de notas.
