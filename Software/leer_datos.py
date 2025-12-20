import socket
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import csv
from datetime import datetime
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
UDP_IP = "0.0.0.0"
UDP_PORT = 4210
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
sock.setblocking(False)

# --- CSV DE DATOS ---
csv_path = f"/Users/alexasessarego/Documents/DatosPacientes/{filename}.csv" # path datos
data_csv = open(csv_path, "w", newline="")
data_writer = csv.writer(data_csv)
data_writer.writerow(["Timestamp", "Yaw", "Pitch", "Roll", "Ax", "Ay", "Az"])

# --- CSV DE ACTIVIDADES ---
act_csv_path = f"/Users/alexasessarego/Documents/DatosPacientes/Notas_{filename}.csv" # path actividades
act_csv = open(act_csv_path, "w", newline="")
act_writer = csv.writer(act_csv)
act_writer.writerow(["inicio", "fin", "actividad"])

# --- VARIABLES DE ANIMACIÓN ---
max_len = 50
yaw_data = deque([0]*max_len, maxlen=max_len)
pitch_data = deque([0]*max_len, maxlen=max_len)
roll_data = deque([0]*max_len, maxlen=max_len)

fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.2)  # espacio para botones
line_yaw, = ax.plot([], [], label='Yaw', color='r')
line_pitch, = ax.plot([], [], label='Pitch', color='g')
line_roll, = ax.plot([], [], label='Roll', color='b')
ax.set_ylim(-180, 180)
ax.set_xlim(0, max_len)
ax.set_xlabel('Tiempo')
ax.set_ylabel('Grados')
ax.legend()
ax.grid(True)

# --- ACTIVIDAD ACTUAL ---
actividad_actual = None
inicio_actual = None

def nueva_actividad(event):
    global actividad_actual, inicio_actual
    texto = text_box.text.strip()
    if not texto:
        return
    ahora = datetime.now()
    # cerrar actividad anterior
    if actividad_actual is not None:
        act_writer.writerow([
            inicio_actual.strftime("%H:%M:%S.%f")[:-3],
            ahora.strftime("%H:%M:%S.%f")[:-3],
            actividad_actual
        ])
        act_csv.flush()
        print(f"Actividad registrada: {actividad_actual} {inicio_actual} - {ahora}")
    # iniciar nueva actividad
    actividad_actual = texto
    inicio_actual = ahora
    text_box.set_val("")  # limpiar textbox

# --- BOTON Y TEXTBOX ---
axbox = plt.axes([0.1, 0.05, 0.5, 0.05])
text_box = TextBox(axbox, "Nueva actividad")

# Enlazamos la función al evento "submit" (Enter)
text_box.on_submit(nueva_actividad)

# --- Boton registrar como opcion en vez de enter ---
axbtn = plt.axes([0.65, 0.05, 0.2, 0.05])
btn = Button(axbtn, "Registrar")
btn.on_clicked(lambda event: nueva_actividad(None))  # mismo efecto que Enter

# --- FUNCION DE ANIMACIÓN ---
def update(frame):
    last_data = None
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            last_data = data
        except BlockingIOError:
            break

    if last_data is not None:
        try:
            values = [float(x) for x in last_data.decode('utf-8').strip().split(',')[1:]]
            yaw, pitch, roll, ax_val, ay_val, az_val = values
            yaw_data.append(yaw)
            pitch_data.append(pitch)
            roll_data.append(roll)
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            data_writer.writerow([timestamp, yaw, pitch, roll, ax_val, ay_val, az_val])
        except ValueError:
            pass

    line_yaw.set_data(range(len(yaw_data)), yaw_data)
    line_pitch.set_data(range(len(pitch_data)), pitch_data)
    line_roll.set_data(range(len(roll_data)), roll_data)
    return line_yaw, line_pitch, line_roll

# --- ANIMACION ---
ani = animation.FuncAnimation(fig, update, interval=5, blit=False)
plt.show()

# --- AL CERRAR ---
data_csv.close()
# cerrar última actividad si existe
if actividad_actual is not None:
    ahora = datetime.now()
    act_writer.writerow([
        inicio_actual.strftime("%H:%M:%S.%f")[:-3],
        ahora.strftime("%H:%M:%S.%f")[:-3],
        actividad_actual
    ])
act_csv.close()
