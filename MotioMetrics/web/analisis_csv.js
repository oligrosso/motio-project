// URL del backend en Render
const API_URL = "https://motiometrics-backend.onrender.com"; 

const { jsPDF } = window.jspdf; // Importar jsPDF desde la ventana global

const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');
const spinner = document.getElementById('spinner');
const btnExport = document.getElementById('btnExport');
const btnGuardar = document.getElementById('btnGuardarPaciente');

// Variables globales para guardar estado
let datosAnalisis = null; // Aquí guardaremos la respuesta del backend
let observaciones = [];   // Aquí acumularemos las observaciones

// Variables globales para pacientes (simulación de DB)
let pacientes = JSON.parse(localStorage.getItem('pacientes')) || []; // Cargar de LocalStorage
let pacienteActual = null; // Paciente seleccionado
let registrosMostrados = 5; // Límite inicial para la tabla

// Variable global para hora de inicio con miniSD
let horaInicioMedicion = null;  // Guardará la hora que ponga el usuario (formato "HH:MM")

// --- 1. MANEJO DE ARCHIVOS (Drag & Drop) ---

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length) handleFileUpload(files[0]);
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) handleFileUpload(e.target.files[0]);
});

// Deshabilitar guardar al inicio
document.addEventListener('DOMContentLoaded', () => {
  // document.getElementById('btnGuardarPaciente').disabled = true; (dejar botón siempre habilitado, en el clic despues analiza si desabilitar)
  actualizarTablaHistoria();
});

async function handleFileUpload(file) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
        alert("Por favor sube un archivo .csv válido.");
        return;
    }

    // ---- NUEVO: Mostrar modal de confirmación ----
    document.getElementById('modalConfirm').style.display = 'block';
    document.getElementById('modalOverlay').style.display = 'block';

    // Guardamos el file para usarlo después
    window.filePendiente = file;

    // Detenemos la ejecución hasta que responda el usuario
    return;

    // Limpiamos estados previos al iniciar
    //dropzone.classList.remove('success', 'error');
    //dropzone.classList.add('loading');
    //dropzone.innerHTML = `Analizando <strong>${file.name}</strong>...`;
    //spinner.style.display = 'block';

    //toggleLoadingState(true);

    //const formData = new FormData();
    //formData.append('file', file);

    //try {
        const response = await fetch(`${API_URL}/api/analizar_datos`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Error en el análisis del servidor');

        const data = await response.json();
        datosAnalisis = data; // Guardamos datos para el reporte
        toggleLoadingState(false);
        mostrarResultados(data);

        dropzone.classList.remove('loading');
        dropzone.classList.add('success');
        dropzone.innerHTML = `<strong>${file.name}</strong> analizado correctamente.`;

    //} catch (error) {
        console.error(error);
        toggleLoadingState(false);
        limpiarResultados();
        dropzone.classList.remove('loading');
        dropzone.classList.add('error');
        dropzone.textContent = "Error al procesar el archivo.";
    //} finally {
        spinner.style.display = 'none';
    //}
}

// --- LÓGICA DEL MODAL DE CONFIRMACIÓN ---

document.getElementById('btnModalNo').addEventListener('click', () => {
    document.getElementById('modalConfirm').style.display = 'none';
    document.getElementById('modalOverlay').style.display = 'none';
    alert("Continuá con la carga de datos.");
    // Procede con análisis normal (sin hora inicio)
    procesarArchivoPendiente(null); // null = no hay hora inicio
});

document.getElementById('btnModalSi').addEventListener('click', () => {
    document.getElementById('modalConfirm').style.display = 'none';
    document.getElementById('modalHoraInicio').style.display = 'block';
});

document.getElementById('btnHoraContinuar').addEventListener('click', () => {
    const hora = document.getElementById('inputHoraInicio').value;
    if (!hora) {
        alert("Por favor ingresá la hora de inicio.");
        return;
    }
    
    // Cerrar modal hora
    document.getElementById('modalHoraInicio').style.display = 'none';
     // Mostrar mensaje final antes de analizar
    alert("Continuar con la carga de datos.");
    document.getElementById('modalOverlay').style.display = 'none';
    procesarArchivoPendiente(hora); // pasa la hora
});

// Función que hace el análisis real (la que tenía handleFileUpload)
async function procesarArchivoPendiente(horaInicio) {
    horaInicioMedicion = horaInicio; // Guardamos global para gráficos

    const file = window.filePendiente;
    if (!file) return; // Seguridad

    // Limpiamos estados previos al iniciar
    dropzone.classList.remove('success', 'error');
    dropzone.classList.add('loading');
    dropzone.innerHTML = `Analizando <strong>${file.name}</strong>...`;
    spinner.style.display = 'block';
    toggleLoadingState(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_URL}/api/analizar_datos`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Error en el análisis del servidor');

        const data = await response.json();
        datosAnalisis = data; // Guardamos datos para el reporte
        toggleLoadingState(false);
        mostrarResultados(data);

        dropzone.classList.remove('loading');
        dropzone.classList.add('success');
        dropzone.innerHTML = `<strong>${file.name}</strong> analizado correctamente.`;

    } catch (error) {
        console.error(error);
        toggleLoadingState(false);
        limpiarResultados();
        dropzone.classList.remove('loading');
        dropzone.classList.add('error');
        dropzone.textContent = "Error al procesar el archivo.";
    } finally {
        spinner.style.display = 'none';
    }

    window.filePendiente = null; // limpia
}

function mostrarResultados(data) {
    // VER SI SIRVE: si horaInicioMedicion existe, se pone como label
    const labelHora = horaInicioMedicion ? ` (inicio: ${horaInicioMedicion})` : '';
    // y en title del gráfico RMS:
    //title: `Energía del Temblor (RMS) en el Tiempo${labelHora}`,
    
    
    // === 1. Actualizar métricas principales ===
    document.getElementById('valor-f-dom').textContent = `${data.metricas.frecuencia_dominante} Hz`;
    document.getElementById('valor-psd-peak').textContent = data.metricas.psd_pico.toFixed(2);
    
    // Actualizar texto de estado de temblor
    const textoEstado = document.getElementById('texto-estado-temblor');
    if (data.metricas.tiene_temblor) {
        textoEstado.textContent = "Se detectó temblor";
        textoEstado.style.color = "var(--error)";  // Rojo para alerta
        textoEstado.classList.remove('muted');     // Quitar muted para que sea más visible
    } else {
        textoEstado.textContent = "No se detectó temblor";
        textoEstado.style.color = "var(--success)";  // Verde para OK
        textoEstado.classList.remove('muted');
    }

    // === 2. Gráfico 1: PSD vs Frecuencia (Burg) con línea roja de frecuencia dominante ===
    const f_dom = data.metricas.frecuencia_dominante;
    const psd_max = Math.max(...data.graficos.freq_y);

    const tracePSD = {
        x: data.graficos.freq_x,
        y: data.graficos.freq_y,
        type: 'scatter',
        mode: 'lines',
        name: 'PSD Promedio',
        line: { color: '#0284c7', width: 2.5 }
    };

    const traceDominante = {
        x: [f_dom, f_dom],
        y: [0, psd_max * 1.1],  // un poco más arriba del pico
        mode: 'lines',
        line: { color: 'red', width: 2, dash: 'dash' },
        name: `F. dominante: ${f_dom.toFixed(2)} Hz`,
        hoverinfo: 'none'
    };

    const puntoDominante = {
        x: [f_dom],
        y: [psd_max],
        mode: 'markers',
        marker: { color: 'red', size: 10 },
        name: 'Pico dominante',
        hoverinfo: 'none'
    };

    // Calculamos Nyquist usando el SR que viene del backend
    const nyquist = data.metricas.sr / 2;

    Plotly.newPlot('chartFreqAmp', [tracePSD, traceDominante, puntoDominante], {
        title: 'PSD vs Frecuencia (Método de Burg)',
        xaxis: { title: 'Frecuencia (Hz)', range: [0, nyquist] }, // <--- CAMBIO: Límite dinámico
        yaxis: { title: 'PSD (Potencia)' },
        height: 420,
        margin: { t: 50, b: 50, l: 60, r: 30 },
        hovermode: 'x unified',
        legend: { x: 0.02, y: 0.98, bgcolor: 'rgba(255,255,255,0.8)' }
    });

    // === AJUSTE DE TIEMPO REAL SI VIENE DE SD ===
    //let ejeTiempo = data.graficos.tiempo;

    //if (horaInicioMedicion) {
        // horaInicioMedicion viene como "HH:MM"
      //  const [h, m] = horaInicioMedicion.split(':').map(Number);

        // Fecha base (hoy, solo para Plotly)
        //const base = new Date();
        //base.setHours(h, m, 0, 0);

        //ejeTiempo = data.graficos.tiempo.map((_, i) => {
            // cada punto se separa por dt segundos
          //  const dt = (i * data.graficos.dt) * 1000; // ms
            //return new Date(base.getTime() + dt);
        //});
    //}

    // --- Helpers ---
    function parseHMSmsToMs(t) {
    // acepta "HH:MM:SS.mmm" o "HH:MM:SS"
    const [hh, mm, rest] = t.split(':');
    const [ss, ms = '0'] = rest.split('.');
    return (
        (Number(hh) * 3600 + Number(mm) * 60 + Number(ss)) * 1000 +
        Number(ms.padEnd(3, '0').slice(0, 3))
    );
    }

    function parseTimeStringToEpochMs(t) {
    // backend a veces manda "1900-01-01 00:00:07.390000"
    // o algo parseable por Date. Convertimos " " -> "T"
    const iso = t.includes(' ') ? t.replace(' ', 'T') : t;
    const ms = Date.parse(iso);
    return Number.isFinite(ms) ? ms : NaN;
    }

    // --- Construcción del eje X ---
    let ejeTiempoRaw = data.graficos.tiempo || [];
    let ejeTiempo; // lo que va a Plotly

    // Detectar si "tiempo" viene con fecha tipo "1900-01-01 ..."
    const rawHasDate = ejeTiempoRaw.length && /[-/]/.test(ejeTiempoRaw[0]);

    // Calculamos elapsedMs[] (tiempo transcurrido desde el primer punto)
    let elapsedMs = [];

    if (rawHasDate) {
    const t0 = parseTimeStringToEpochMs(ejeTiempoRaw[0]);
    elapsedMs = ejeTiempoRaw.map(t => parseTimeStringToEpochMs(t) - t0);
    } else {
    // si viniera puro "HH:MM:SS.mmm"
    elapsedMs = ejeTiempoRaw.map(t => parseHMSmsToMs(t) - parseHMSmsToMs(ejeTiempoRaw[0]));
    }

    if (horaInicioMedicion) {
    const [h, m] = horaInicioMedicion.split(':').map(Number);
    const base = new Date();
    base.setHours(h, m, 0, 0);

    ejeTiempo = elapsedMs.map(ms => new Date(base.getTime() + ms));
    } else {
    // Sin SD: podés graficar directo como Date también (más consistente)
    if (rawHasDate) {
        ejeTiempo = ejeTiempoRaw.map(t => new Date(parseTimeStringToEpochMs(t)));
    } else {
        // si fuera HH:MM:SS.mmm sin fecha, lo anclamos a "hoy 00:00"
        const base = new Date();
        base.setHours(0, 0, 0, 0);
        ejeTiempo = elapsedMs.map(ms => new Date(base.getTime() + ms));
    }
    }


    // === 3. Gráfico 2: RMS vs Tiempo con episodios de temblor en verde ===
    const traceRMS = {
        x: ejeTiempo,
        y: data.graficos.rms,
        type: 'scatter',
        mode: 'lines',
        name: 'RMS Combinado',
        line: { color: '#2e7cf1ff', width: 2 },
        fill: 'tozeroy',
        fillcolor: 'rgba(112, 150, 207, 0.15)'
    };

    // <<< EPISODIOS DE TEMBLOR (fondos verdes) >>>
    const episodios = data.graficos.episodios || [];  // El backend ahora los manda

    function episodioToX(epTimeStr) {
        if (!horaInicioMedicion) {
            // sin SD: lo convertimos a Date (mismo tipo que ejeTiempo)
            const ms = parseTimeStringToEpochMs(epTimeStr);
            return Number.isFinite(ms) ? new Date(ms) : epTimeStr;
        }

        // con SD: convertimos a elapsed desde t0 y lo sumamos a base
        const ms = parseTimeStringToEpochMs(epTimeStr);
        const t0 = rawHasDate ? parseTimeStringToEpochMs(ejeTiempoRaw[0]) : NaN;
        const rel = Number.isFinite(ms) && Number.isFinite(t0) ? (ms - t0) : 0;

        const [h, m] = horaInicioMedicion.split(':').map(Number);
        const base = new Date();
        base.setHours(h, m, 0, 0);

        return new Date(base.getTime() + rel);
    }

    const shapes = episodios.map(ep => ({
        type: 'rect',
        xref: 'x',
        yref: 'paper',      // Cubre todo el alto del gráfico
        x0: episodioToX(ep.inicio),      // Ej: "08:31:20"
        x1: episodioToX(ep.fin),         // Ej: "08:31:50"
        y0: 0,
        y1: 1,
        fillcolor: 'rgba(34, 197, 94, 0.3)',  // Verde suave (como lightgreen)
        line: { width: 0 },
        layer: 'below'
    }));

    // Opcional: agregar etiquetas de amplitud (como en Python)
    const maxRms = Math.max(...(data.graficos.rms || [1]));
    const annotations = episodios.map(ep => ({
        x: episodioToX(ep.fin),
        y: maxRms * 0.95,  // Cerca del max Y
        xref: 'x',
        yref: 'y',
        text: `${ep.amplitud}`,
        showarrow: false,
        font: { color: 'green', size: 10, weight: 'bold' },
        align: 'right',
        bgcolor: 'rgba(255,255,255,0.8)',
        borderpad: 2
    }));

    Plotly.newPlot('chartRMSTime', [traceRMS], { 

        title: 'Energía del Temblor (RMS) en el Tiempo',
        xaxis: { title: 'Tiempo (%H:%M:%S)',
                tickformat: '%H:%M:%S',  // ← Esto fuerza SOLO HH:MM:SS (saca fecha)
                hoverformat: '%H:%M:%S'  // ← Mouse también sin fecha
         },
        yaxis: { title: 'Amplitud RMS (°)' },
        height: 420,
        margin: { t: 50, b: 50, l: 60, r: 30 },
        hovermode: 'x unified',
        shapes: shapes,          // <<< Fondos verdes
        annotations: annotations // <<< Etiquetas de amplitud (opcional, podés borrar si no querés)
    }, {responsive: true});

    console.log('Episodios recibidos:', episodios);
    
    // Actualizar si hay temblor (el backend devuelve "tiene_temblor" en data.metricas)
    const detectoTemblor = data.metricas.tiene_temblor || false; 
}

// --- 2. GESTIÓN DE OBSERVACIONES ---

document.getElementById('btnAddObservation').addEventListener('click', () => {
    const desc = document.getElementById('obsDescription').value;
    const start = document.getElementById('obsStartTime').value;
    const end = document.getElementById('obsEndTime').value;

    if (!desc) {
        alert("Escribe una descripción para la observación.");
        return;
    }

    const obs = {
        descripcion: desc,
        inicio: start || "--:--",
        fin: end || "--:--"
    };

    observaciones.push(obs);
    renderObservaciones();
    
    // Limpiar inputs
    document.getElementById('obsDescription').value = "";
    document.getElementById('obsStartTime').value = "";
    document.getElementById('obsEndTime').value = "";
});

function renderObservaciones() {
    const list = document.getElementById('observationList');
    if (observaciones.length === 0) {
        list.innerHTML = "No hay observaciones.";
        return;
    }
    
    let html = '<ul style="padding-left: 20px; margin: 0;">';
    observaciones.forEach((obs, index) => {
        html += `<li style="margin-bottom: 4px;">
            <strong>[${obs.inicio} - ${obs.fin}]</strong> ${obs.descripcion}
        </li>`;
    });
    html += '</ul>';
    list.innerHTML = html;
}

// --- 3. GENERACIÓN Y EXPORTACIÓN DE PDF ---

btnExport.addEventListener('click', async () => {
    if (!window.jspdf) {
        alert("Error: La librería jsPDF no se cargó correctamente. Recarga la página.");
        return;
    }

    const { jsPDF } = window.jspdf;
    const doc = new jsPDF("p", "mm", "a4"); // Formato A4 vertical
    const pageHeight = doc.internal.pageSize.height;

    // Obtener datos actuales del formulario
    const pName = document.getElementById('nombrePaciente').value || "Paciente";
    const pId = document.getElementById('idHistoria').value || "---";
    const pAge = document.getElementById('edadPaciente').value || "--";
    const pGender = document.getElementById('generoPaciente').value || "--";
    const today = new Date().toLocaleDateString().replace(/\//g, '-'); // Formato dd-mm-yyyy

    // --- PÁGINA 1: TEXTO Y DATOS ---
    
    // Encabezado Azul
    doc.setFillColor(16, 44, 89); // Azul oscuro corporativo
    doc.rect(0, 0, 210, 25, 'F'); // Barra superior
    
    // LOGO (Usamos el logo oculto específico para PDF)
    try {
        // CAMBIO: Buscamos el ID del logo oculto
        const logoImg = document.getElementById('pdf-logo-hidden');
        if (logoImg && logoImg.complete) {
            const logoData = getBase64Image(logoImg);
            doc.addImage(logoData, 'PNG', 10, 5, 15, 15); // Logo en x=10
        }
    } catch(e) { console.log("Logo no disponible para PDF", e); }

    // Título
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(20);
    doc.setFont("helvetica", "bold");
    doc.text("MotioMetrics", 28, 17); // Texto desplazado a la derecha del logo
    
    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");
    doc.text("Informe Clínico de Temblor", 200, 17, { align: "right" });


    let y = 40;
    
    // Datos Paciente
    doc.setTextColor(0, 0, 0);
    doc.setFontSize(14);
    doc.setFont("helvetica", "bold");
    doc.text("Datos del Paciente", 10, y);
    doc.line(10, y+2, 200, y+2);
    y += 8;

    doc.setFontSize(11);
    doc.setFont("helvetica", "normal");
    doc.text(`Nombre: ${pName}`, 10, y);
    doc.text(`ID: ${pId}`, 110, y);
    y += 6;
    doc.text(`Edad: ${pAge}`, 10, y);
    doc.text(`Género: ${pGender}`, 110, y);
    y += 6;
    doc.text(`Fecha reporte: ${new Date().toLocaleDateString()}`, 10, y);

    y += 12;

    // Métricas
    if (datosAnalisis) {
        doc.setFontSize(14);
        doc.setFont("helvetica", "bold");
        doc.text("Métricas Principales", 10, y);
        doc.line(10, y+2, 200, y+2);
        y += 8;

        // Caja destacada
        doc.setFillColor(240, 249, 255);
        doc.rect(10, y, 190, 20, 'F');
        
        doc.setFontSize(12);
        doc.setTextColor(16, 44, 89);
        doc.text(`Frecuencia Dominante: ${datosAnalisis.metricas.frecuencia_dominante} Hz`, 15, y+8);
        doc.text(`Pico de Potencia (PSD): ${datosAnalisis.metricas.psd_pico}`, 15, y+15);
        
        y += 28;
    }

    // Observaciones
    doc.setTextColor(0, 0, 0);
    doc.setFontSize(14);
    doc.setFont("helvetica", "bold");
    doc.text("Observaciones Clínicas", 10, y);
    doc.line(10, y+2, 200, y+2);
    y += 8;

    doc.setFontSize(11);
    doc.setFont("helvetica", "normal");
    
    if (observaciones.length === 0) {
        doc.setTextColor(100);
        doc.text("No se registraron observaciones adicionales.", 10, y);
        y += 10;
    } else {
        observaciones.forEach(obs => {
            const linea = `• [${obs.inicio} - ${obs.fin}]: ${obs.descripcion}`;
            const splitText = doc.splitTextToSize(linea, 180);
            doc.text(splitText, 10, y);
            y += (6 * splitText.length);
        });
    }

    // --- PÁGINA 2: GRÁFICOS ---
    if (datosAnalisis) {
        doc.addPage();
        
        doc.setFillColor(16, 44, 89);
        doc.rect(0, 0, 210, 15, 'F');
        doc.setTextColor(255);
        doc.setFontSize(10);
        doc.text("MotioMetrics - Gráficos", 10, 10);

        let imgY = 25;
        const chartHeight = 75;

        try {

            // Pequeña pausa para que Plotly termine de dibujar shapes y annotations
            await new Promise(resolve => setTimeout(resolve, 500)); // 0.5 segundos

            // Gráfico 1: PSD vs Frecuencia
            const chart1 = document.getElementById('chartFreqAmp');
            if (chart1 && chart1.data && chart1.data.length > 0) {
                const img1 = await Plotly.toImage(chart1, {format: 'png', width: 1000, height: 500});
                doc.addImage(img1, 'PNG', 15, imgY, 180, chartHeight);
                imgY += chartHeight + 10;
                doc.text("PSD vs Frecuencia (Método de Burg)", 15, imgY - chartHeight - 5);

            //if (document.getElementById('chartFreqAmp').data) {
            //    const img1 = await Plotly.toImage(document.getElementById('chartFreqAmp'), {format: 'png', width: 800, height: 400});
            //    doc.addImage(img1, 'PNG', 15, imgY, 180, chartHeight);
            //    imgY += chartHeight + 10;
            }
            
            // Gráfico 2: RMS vs Tiempo (con fondos verdes)
            const chart2 = document.getElementById('chartRMSTime');
            if (chart2 && chart2.data && chart2.data.length > 0) {
                // Si no cabe en la página actual → nueva página
                if ((imgY + chartHeight) > (pageHeight - 20)) {
                    doc.addPage();
                    imgY = 20;
                    doc.setFillColor(16, 44, 89);
                    doc.rect(0, 0, 210, 15, 'F');
                    doc.setTextColor(255);
                    doc.setFontSize(10);
                    doc.text("MotioMetrics - Gráficos (continuación)", 10, 10);
                }

                const img2 = await Plotly.toImage(chart2, {format: 'png', width: 1000, height: 500});
                doc.addImage(img2, 'PNG', 15, imgY, 180, chartHeight);
                imgY += chartHeight + 10;
                doc.text("Energía del Temblor (RMS) en el Tiempo", 15, imgY - chartHeight - 5);
            }

            if (imgY === 25) {
                // Si no se agregó ningún gráfico → mensaje
                doc.setTextColor(100);
                doc.setFontSize(12);
                doc.text("No se pudieron capturar los gráficos (posible error de renderizado).", 15, imgY);
            }


            //if (document.getElementById('chartRMSTime').data) {
                // Nueva página si no cabe
            //    if ((imgY + chartHeight) > (pageHeight - 10)) {
            //         doc.addPage();
            //         imgY = 20;
            //    }
                
            //    const img2 = await Plotly.toImage(document.getElementById('chartRMSTime'), {format: 'png', width: 800, height: 400});
            //    doc.addImage(img2, 'PNG', 15, imgY, 180, chartHeight);
            //}
        } catch (err) {
            console.error("Error capturando gráficos para PDF:", err);
            doc.setTextColor(200, 0, 0);
            doc.setFontSize(12);
            doc.text("Error al generar gráficos en el PDF. Ver consola del navegador.", 15, imgY);
            doc.text("Posible causa: shapes/annotations complejos en Plotly.", 15, imgY + 10);
        }
    }
    
    const safeName = `${pName.replace(/\s+/g, '_')}_${today}_Motio.pdf`;

    // --- LÓGICA DE GUARDADO ---
    if (window.pywebview) {
        // MODO ESCRITORIO (.EXE)
        // 1. Convertimos el PDF a una cadena Base64 (un texto largo que representa el archivo)
        const pdfOutput = doc.output('datauristring');
        // El string viene como "data:application/pdf;base64,JVBERi0xIg...", hay que sacar la primera parte
        const pdfBase64 = pdfOutput.split(',')[1]; 

        // 2. Se lo mandamos a Python
        window.pywebview.api.guardar_pdf_dialogo(pdfBase64, safeName)
            .then((guardado) => {
                if(guardado) {
                    alert("Informe PDF guardado correctamente.");
                }
            })
            .catch(err => alert("Error al guardar el PDF: " + err));

    } else {
        // MODO WEB (Chrome normal)
        doc.save(safeName);
    }
});

// Función auxiliar para convertir imagen HTML (logo) a Base64
function getBase64Image(img) {
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);
    return canvas.toDataURL("image/png");
}

// Función auxiliar para activar/desactivar spinners
function toggleLoadingState(isLoading) {
    // Referencias a los loaders
    const loaderMetrics = document.getElementById('loader-metrics');
    const loaderChart1 = document.getElementById('loader-chart1');
    const loaderChart2 = document.getElementById('loader-chart2');
    const loaderHistory = document.getElementById('loader-history');

    // Referencias a los contenidos que queremos ocultar/mostrar
    const contentMetrics = document.getElementById('content-metrics');
    const chartFreq = document.getElementById('chartFreqAmp');
    const chartTime = document.getElementById('chartRMSTime');
    const contentHistory = document.getElementById('content-history');

    if (isLoading) {
        // MOSTRAR LOADERS
        if(loaderMetrics) loaderMetrics.style.display = 'block';
        if(loaderChart1) loaderChart1.style.display = 'block';
        if(loaderChart2) loaderChart2.style.display = 'block';
        if(loaderHistory) loaderHistory.style.display = 'block';

        // OCULTAR CONTENIDO (opcional, para que no se vea feo mientras carga)
        if(contentMetrics) contentMetrics.style.display = 'none';
        if(chartFreq) chartFreq.style.display = 'none';
        if(chartTime) chartTime.style.display = 'none';
        if(contentHistory) contentHistory.style.display = 'none';

    } else {
        // OCULTAR LOADERS
        if(loaderMetrics) loaderMetrics.style.display = 'none';
        if(loaderChart1) loaderChart1.style.display = 'none';
        if(loaderChart2) loaderChart2.style.display = 'none';
        if(loaderHistory) loaderHistory.style.display = 'none';

        // MOSTRAR CONTENIDO
        if(contentMetrics) contentMetrics.style.display = 'grid'; // Grid para métricas
        if(chartFreq) chartFreq.style.display = 'block';
        if(chartTime) chartTime.style.display = 'block';
        if(contentHistory) contentHistory.style.display = 'block';
    }
}

// Función Limpiar gráficos si hay error

function limpiarResultados() {
    // 1. Resetear variables globales
    datosAnalisis = null;

    // 2. Resetear textos de métricas
    document.getElementById('valor-f-dom').textContent = "-- Hz";
    document.getElementById('valor-psd-peak').textContent = "--";
    
    const textoEstado = document.getElementById('texto-estado-temblor');
    textoEstado.textContent = "Valores promedio calculados.";
    textoEstado.style.color = ""; // Quitar color verde/rojo
    textoEstado.classList.add('muted');

    // 3. Borrar Gráficos (Plotly tiene una función para limpiar)
    try {
        Plotly.purge('chartFreqAmp');
        Plotly.purge('chartRMSTime');
    } catch (e) {
        // Si no había gráficos creados, no pasa nada
        document.getElementById('chartFreqAmp').innerHTML = "";
        document.getElementById('chartRMSTime').innerHTML = "";
    }
}

// Autocompletado en nombre
const inputNombre = document.getElementById('nombrePaciente');
const datalist = document.getElementById('sugerenciasPacientes');

// Al foco: Mostrar primeras 5
inputNombre.addEventListener('focus', () => {
  datalist.innerHTML = '';
  pacientes.slice(0,5).forEach(p => {
    const option = document.createElement('option');
    option.value = p.nombre;
    option.textContent = `${p.nombre} (${p.idHistoria})`;
    datalist.appendChild(option);
  });
});

// Al escribir: Filtrar dinámicamente (max 5)
inputNombre.addEventListener('input', (e) => { // 'input': Se dispara cada vez que cambiás el texto (escribís o borrás). Así, cuando borrás todo, detecta texto vacío y limpia al instante.
  if (texto === '') {
    document.getElementById('idHistoria').value = '';
    document.getElementById('edadPaciente').value = '';
    document.getElementById('generoPaciente').value = 'Seleccionar...';
    pacienteActual = null;
    actualizarTablaHistoria();
  }
  const texto = e.target.value.toLowerCase().trim();
  datalist.innerHTML = ''; // Limpia sugerencias viejas

  if (texto.length < 1) return; // Si vacío, no muestra

  // Filtra pacientes que coincidan (por nombre o idHistoria)
  const sugerencias = pacientes.filter(p => 
    p.nombre.toLowerCase().includes(texto) || p.idHistoria.toLowerCase().includes(texto)
  ).slice(0,5);

  // Agrega opciones al datalist
  sugerencias.forEach(p => {
    const option = document.createElement('option');
    option.value = p.nombre; // Muestra nombre, pero podés agregar ID si querés
    option.textContent = `${p.nombre} (${p.idHistoria})`; // Ej: Juan Pérez (123456)
    datalist.appendChild(option);
  });
});

// Al seleccionar: Autocompletar. 'change' event → Se dispara cuando elegís una opción del dropdown (o presionás enter).
inputNombre.addEventListener('change', (e) => {
  const seleccionado = e.target.value.trim();
  if (!seleccionado) return;

  // Busca el paciente exacto por nombre (o ajustá por ID si preferís)
  const paciente = pacientes.find(p => p.nombre === seleccionado);
  if (!paciente) return; // No error, continua manual

  pacienteActual = paciente;

  document.getElementById('idHistoria').value = paciente.idHistoria;
  document.getElementById('edadPaciente').value = paciente.edad;
  document.getElementById('generoPaciente').value = paciente.genero;
  // Posición y fecha quedan vacíos

  actualizarTablaHistoria();
  alert(`Paciente cargado: ${paciente.nombre}`);
});

// Al hacer click fuera (blur): Limpia si quedó vacío
inputNombre.addEventListener('blur', (e) => {
  if (!e.target.value.trim()) { // ← Pregunta: ¿el campo está vacío (sin letras)?
    e.target.value = ''; // ← Solo SI está vacío, lo limpia (para que vuelva el placeholder perfecto)
  }
});

// **********************************************************************************************
// ------------LocalStorage, botones buscar/guardar y manejo de la tabla con límite-------------
// **********************************************************************************************

// Función para generar ID único simple
function generarId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2); 
  // Date.now() → número gigante del timestamp actual (ms)
  // convertidos a base 36 para que queden más cortos (mezcla de letras y números).
  // Sirve para darle un ID único a cada paciente nuevo.
}

// Botón Guardar Paciente
// Cuando el usuario hace click en el botón, se toman los valores del formulario.
document.getElementById('btnGuardarPaciente').addEventListener('click', () => {
  // 1. Chequeamos si hay resultados del análisis (deben estar disponibles en datosAnalisis)
  if (!datosAnalisis) {
    alert('Primero cargá un archivo CSV y esperá los resultados para guardar un paciente.'); // Evita que guardes un paciente sin análisis para cargarle el registro clínico.
    return; // Corta todo si no hay CSV
  }

  // 2. Ahora chequeamos campos del paciente
  const nombre = document.getElementById('nombrePaciente').value.trim(); // .trim borra espacios al inicio o fin
  const idHistoria = document.getElementById('idHistoria').value.trim();
  const edad = parseInt(document.getElementById('edadPaciente').value); // parseInt convierte edad en numero
  const genero = document.getElementById('generoPaciente').value;
  const posicion = document.getElementById('posicionDispositivo').value;
  const fechaMedicion = document.getElementById('fechaMedicion').value;

  if (!nombre || !idHistoria || isNaN(edad) || genero === 'Seleccionar...' || posicion === 'Seleccionar...' || !fechaMedicion) {
    alert('Completa todos los campos.'); // si falta algo corta la ejecución: Es un pop-up que bloquea la pantalla hasta que el usuario toca Aceptar.
    return;
  }

  // Toma valores de análisis que se realizaron en el backend
  const freqDom = datosAnalisis.metricas.frecuencia_dominante;
  const psdPico = datosAnalisis.metricas.psd_pico;
  const detectoTemblor = datosAnalisis.metricas.tiene_temblor || false; // or false por si el backend falla, pero en realidad no hace falta

  // nuevo registro que se agrega a registros del paciente
  const nuevoRegistro = {
    fecha: fechaMedicion,
    temblor: detectoTemblor,
    freqDom: freqDom,
    psdPico: psdPico,
    posicion: posicion
  };

  // Buscar si el paciente ya existe (por idHistoria)
  let paciente = pacientes.find(p => p.idHistoria === idHistoria);
  if (paciente) { // si ya existe
    // Actualizar datos y agregar registro
    paciente.nombre = nombre;
    paciente.edad = edad;
    paciente.genero = genero;
    paciente.registros.push(nuevoRegistro);
  } else {
    // Nuevo paciente
    paciente = {
      id: generarId(),
      nombre,
      idHistoria,
      edad,
      genero,
      registros: [nuevoRegistro]
    };
    pacientes.push(paciente);
  }

  // Guardar en LocalStorage
  localStorage.setItem('pacientes', JSON.stringify(pacientes)); // Convierte el array pacientes a JSON y lo guarda en el navegador. Así no se pierde aunque se refresque la página.
  pacienteActual = paciente;
  alert('Paciente guardado exitosamente.'); // Deja en memoria cuál es el paciente que se acaba de guardar.

  // Actualizar tabla de historia
  actualizarTablaHistoria(); // Refresca el HTML para mostrar los registros del paciente.
});


// Función para actualizar la tabla de historia
function actualizarTablaHistoria() {
  const tbody = document.querySelector('#tableHistory tbody');
  const verMasContainer = document.getElementById('verMasContainer');
  tbody.innerHTML = ''; // Limpiar todas las filas que había antes

  // Si no hay paciente actual o no tiene registros:
  if (!pacienteActual || pacienteActual.registros.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No hay registros previos</td></tr>';
    verMasContainer.innerHTML = ''; // vacía el contenedor de “Ver más”
    return;
  }

  // Ordenar registros por fecha descendente
  const registrosOrdenados = [...pacienteActual.registros].sort((a, b) => new Date(b.fecha) - new Date(a.fecha)); 
  // [...] → hace una copia del array (para no modificar el original).
  // si b es más nuevo que a, va primero.

  // Mostrar solo los primeros 'registrosMostrados'
  const registrosAMostrar = registrosOrdenados.slice(0, registrosMostrados); // Si registrosMostrados = 5 → muestra los 5 más recientes.
  registrosAMostrar.forEach(reg => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
    <td>${reg.fecha || '—'}</td>
    <td><strong style="color:${reg.temblor ? '#dc2626' : '#16a34a'}"> ${reg.temblor ? 'Sí' : 'No'}</strong></td>
    <td>${reg.freqDom.toFixed(2)}</td>
    <td>${reg.psdPico.toFixed(2)}</td>
    <td>${reg.posicion || '—'}</td>
    `;
    tbody.appendChild(tr);
  });

  // Si hay más, mostrar botón "Ver más..."
  if (registrosOrdenados.length > registrosMostrados) { // Si hay más registros totales que los que estás mostrando ahora (registrosMostrados) → pone el botón.
    verMasContainer.innerHTML = '<button class="btn-ver-mas" id="btnVerMas">Ver más...</button>';
    if (registrosMostrados > 5) {
        verMasContainer.innerHTML += '<button class="btn-ver-mas" id="btnVerMenos" style="margin-left: 10px;">Ver menos...</button>';
        document.getElementById('btnVerMenos').addEventListener('click', () => {
            registrosMostrados = 5;
            actualizarTablaHistoria();
        });
    }
    document.getElementById('btnVerMas').addEventListener('click', () => {
    registrosMostrados += 5;
    actualizarTablaHistoria();
    });
  } else {
    verMasContainer.innerHTML = ''; // Si no hay más → borra el botón.
  }
}

// Al cargar la página, resetear mostrados
document.addEventListener('DOMContentLoaded', () => {
  registrosMostrados = 5;
  actualizarTablaHistoria(); // Inicial, si ya cargaste pacienteActual desde localStorage en otra parte, va a mostrar sus registros.
});