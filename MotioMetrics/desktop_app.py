import webview
import os
import sys
import tkinter as tk
import base64  # <--- para decodificar el PDF
from tkinter import filedialog

# Clase API que expondremos a JavaScript
class Api: # conecta JavaScript con tu Windows
    def guardar_archivo_dialogo(self, contenido, nombre_sugerido): # Esta función recibe el texto del CSV (contenido).
        # Usamos tkinter solo para el cuadro de diálogo "Guardar como"
        root = tk.Tk()
        root.withdraw() # Ocultar la ventanita fea de tkinter
        
        archivo_path = filedialog.asksaveasfilename(
            initialfile=nombre_sugerido,
            defaultextension=".csv",
            filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")]
        )
        root.destroy()
        
        if archivo_path:
            # Escribimos el contenido que vino de JavaScript/Backend en tu disco
            with open(archivo_path, 'w', encoding='utf-8') as f:
                f.write(contenido)
            return True # Le avisamos a JS que salió bien
        return False
    
    def guardar_pdf_dialogo(self, contenido_b64, nombre_sugerido):
        root = tk.Tk()
        root.withdraw()

        archivo_path = filedialog.asksaveasfilename(
            initialfile=nombre_sugerido,
            defaultextension=".pdf",
            filetypes=[("Archivos PDF", "*.pdf")]
        )
        root.destroy()

        if archivo_path:
            try:
                # Decodificamos el churro de letras que manda JS y lo guardamos como archivo binario ('wb')
                datos_pdf = base64.b64decode(contenido_b64)
                with open(archivo_path, 'wb') as f:
                    f.write(datos_pdf)
                return True
            except Exception as e:
                print(f"Error guardando PDF: {e}")
        return False

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS # <--- Esto es clave para el .EXE
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if __name__ == '__main__':
    api = Api() # Instanciamos la API, se crea el puente
    
    archivo_inicio = resource_path('index.html') # Buscamos dónde está el HTML usando la función de arriba
    url_inicio = f'file://{os.path.abspath(archivo_inicio)}' 

    window = webview.create_window( # creamos la ventana
        'MotioMetrics Desktop', 
        url=url_inicio,
        width=1200,
        height=800,
        resizable=True,
        js_api=api # <--- AQUÍ CONECTAMOS PYTHON CON JS
    )

    webview.start()

    # El desktop_app.py solo define la página de inicio (home page). Una vez que la ventana se abre, los enlaces (<a href="...">) funcionan internamente y te permiten moverte por toda la aplicación.