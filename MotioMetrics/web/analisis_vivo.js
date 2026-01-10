// URL del backend en Render (DEBES CAMBIARLA CUANDO TENGAS EL LINK REAL DE RENDER)
const API_URL = "https://motiometrics-backend.onrender.com";
// const API_URL = "http://127.0.0.1:5000"; // Para pruebas locales
// SocketIO client - conexión automática
const socket = io(API_URL, {
    transports: ['websocket'],  // Fuerza WebSocket puro (más estable)
    upgrade: false
});

let chart;
//let pollingInterval;
let isConnected = false;

// 1. Inicializar gráfico Chart.js
function initChart() {
    const ctx = document.getElementById('liveChartYPR').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], // Timestamps
            datasets: [
                { label: 'Yaw', data: [], borderColor: 'red', backgroundColor: 'red', borderWidth: 2, tension: 0.1, pointRadius: 0 },
                { label: 'Pitch', data: [], borderColor: 'orange', backgroundColor: 'orange', borderWidth: 2, tension: 0.1, pointRadius: 0 },
                { label: 'Roll', data: [], borderColor: 'green', backgroundColor: 'green', borderWidth: 2, tension: 0.1, pointRadius: 0 } 
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false, // Desactivar animación para mejorar rendimiento en vivo
            scales: {
                y: { min: -180, max: 180 }
            }
        }
    });
}

// Recibe datos en tiempo real del backend
socket.on('datos_vivo', function(data) {
    if (data.labels) {
        updateChart(data);
    }
});

socket.on('connect', () => {
    document.getElementById('connectionStatus').textContent = "Estado: Conectado (Real Time)";
});

socket.on('disconnect', () => {
    document.getElementById('connectionStatus').textContent = "Estado: Desconectado";
});

// 2. Función para conectar/desconectar
document.getElementById('btnConnect').addEventListener('click', async () => {
    const btn = document.getElementById('btnConnect');
    const statusText = document.getElementById('connectionStatus');
    const dashboard = document.getElementById('liveDashboard');
    const connectionPrompt = document.getElementById('connectionPrompt');
    const modalAnalizar = document.getElementById('modalAnalizar');
    const overlay = document.getElementById('modalOverlay');

    if (!isConnected) {
        // --- LÓGICA DE CONEXIÓN ---
        statusText.textContent = "Estado: Conectado";
        const nombreSesion = window.prompt("Ingrese nombre de la sesión:", "Paciente_01") || "sesion";
        try {
            const res = await fetch(`${API_URL}/api/leer_datos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'start', nombre_sesion: nombreSesion })
            });
            
            if (res.ok) {
                isConnected = true;
                btn.textContent = "⏹ Detener Registro";
                btn.classList.replace('btn-primary', 'btn');
                
                // TRANSICIÓN DE UI
                const toolbar = document.querySelector('.toolbar');
                if (toolbar) toolbar.prepend(btn);            // 🔥 mueve el botón fuera del prompt (así no desaparece)
                connectionPrompt.style.display = 'none';      // Oculta "Esperando Conexión"
                dashboard.style.display = 'grid';             // Muestra Gráfico y Anotaciones
                setTimeout(() => {
                    if (chart) chart.resize();
                }, 50);
            }
        } catch (e) { alert("Error de conexión"); }

    } else {
        // --- LÓGICA DE DESCONEXIÓN ---
        statusText.textContent = "Estado: Desconectado";
        try {
            const res = await fetch(`${API_URL}/api/leer_datos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'stop' })
            });
            const data = await res.json();
            window.csvGenerado = data.csv;

            // Descargar archivos (forzado via fetch->blob para que el navegador no bloquee)
            await descargarArchivo(`${API_URL}/grabaciones_vivo/${data.csv}`, data.csv);
            await new Promise(r => setTimeout(r, 300));
            await descargarArchivo(`${API_URL}/grabaciones_vivo/${"Notas_" + data.csv}`, "Notas_" + data.csv);

            // UI Final
            isConnected = false;
            statusText.textContent = "Estado: Desconectado";
            btn.textContent = "🛜 Conectar MotioSensor";
            btn.classList.replace('btn', 'btn-primary');
            if (connectionPrompt) connectionPrompt.appendChild(btn); // vuelve el botón al cuadro para la próxima conexión
            dashboard.style.display = 'none';
            overlay.style.display = 'block';
            modalAnalizar.style.display = 'block';
        } catch (e) { console.error("Error al detener:", e); }
    }
});

// 4. Actualizar Gráfico
function updateChart(data) {
    chart.data.labels = data.labels;
    chart.data.datasets[0].data = data.yaw;
    chart.data.datasets[1].data = data.pitch;
    chart.data.datasets[2].data = data.roll;
    chart.update({duration: 0});
}

document.getElementById('btnNewActivity').addEventListener('click', async () => {
    const input = document.getElementById('activityInput');
    const desc = input.value.trim();
    if (!desc) return;
    
    // Limpiar mensaje de "Aún no hay actividades" si es la primera
    const list = document.getElementById('activityList');
    if (list.querySelector('em')) list.innerHTML = '';

    await fetch(`${API_URL}/api/leer_datos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'anotacion', descripcion: desc })
    });
    
    // AGREGAR VISUALMENTE A LA LISTA
    const li = document.createElement('li');
    li.innerHTML = `<strong>${new Date().toLocaleTimeString()}</strong> ${desc}`;
    list.prepend(li); // Agrega arriba de todo
    
    input.value = '';
});

document.getElementById('activityInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    document.getElementById('btnNewActivity').click();
  }
});


// Botón Analizar del modal
document.getElementById('btnAnalizarCsv').addEventListener('click', () => {
    document.getElementById('modalAnalizar').style.display = 'none';
    document.getElementById('modalOverlay').style.display = 'none';
    
    if (window.csvGenerado) {
        window.location.href = `analisis_csv.html?csv=${window.csvGenerado}`;
    } else {
        alert("No se generó archivo CSV. Intentá de nuevo.");
    }
});

document.getElementById('btnVolverInicio').addEventListener('click', () => {
  document.getElementById('modalAnalizar').style.display = 'none';
  document.getElementById('modalOverlay').style.display = 'none';

  window.location.replace('index.html');
});


// Cerrar modal si clickea fuera
document.getElementById('modalOverlay').addEventListener('click', () => {
    document.getElementById('modalAnalizar').style.display = 'none';
    document.getElementById('modalOverlay').style.display = 'none';
});

// Inicializar al cargar
document.addEventListener('DOMContentLoaded', initChart);

async function descargarArchivo(url, filename) {
    // 1. Descargamos el contenido del Backend (Render) a la memoria
    const res = await fetch(url);
    if (!res.ok) {
        console.error("No se pudo descargar:", filename, res.status);
        alert("Error al descargar el archivo del servidor.");
        return;
    }
    const textoCSV = await res.text(); // Obtenemos el contenido como texto

    // 2. VERIFICAMOS: ¿Estamos dentro del programa .exe (pywebview)?
    if (window.pywebview) {
        // --- MODO ESCRITORIO ---
        // Llamamos a la función Python que creamos arriba
        // 'guardar_archivo_dialogo' es el nombre que pusimos en la clase Api
        window.pywebview.api.guardar_archivo_dialogo(textoCSV, filename)
            .then((guardado) => {
                if(guardado) {
                    alert("Archivo guardado correctamente en tu PC.");
                }
            });
            
    } else {
        // --- MODO WEB (Chrome/Firefox normal) ---
        // Mantenemos tu lógica original por si abres el HTML sin el .exe
        const blob = new Blob([textoCSV], { type: 'text/csv' });
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(objectUrl);
    }
}
