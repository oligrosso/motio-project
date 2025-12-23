/*
 * ========================================================================
 * GUANTE TERAPÉUTICO PARA ENFERMEDAD DE PARKINSON
 * Estimulación de Reset Coordinada Vibrotáctil (vCR)
 * ========================================================================
 * 
 * Basado en investigación de Stanford Medicine (Dr. Peter Tass)
 * Publicación: Frontiers in Physiology, Abril 2021
 * 
 * DESCRIPCIÓN:
 * Este dispositivo aplica vibraciones coordinadas a las yemas de los dedos
 * para desincronizar la actividad neuronal anormal característica del
 * Parkinson's, aliviando síntomas motores y no motores.
 * 
 * PROTOCOLO DE TRATAMIENTO:
 * - Duración: 2 horas por sesión
 * - Frecuencia: 2 sesiones diarias (mañana y tarde/noche)
 * - Frecuencia de vibración: 250 Hz
 * - Dedos estimulados: Índice, medio, anular y meñique
 * 
 * AUTOR: [Tu Nombre]
 * FECHA: Octubre 2024
 * VERSIÓN: 2.0 - Código Completo con Todas las Mejoras
 * ========================================================================
 */

#include <Arduino.h>

// ========================================================================
// CONFIGURACIÓN DE HARDWARE
// ========================================================================

// Pines para los 4 motores de vibración (uno por dedo: índice, medio, anular, meñique)
// NOTA: Se evitan GPIO0 (D3) y GPIO15 (D8) por conflictos en ESP8266 boot
#define MOTOR1 D1  // GPIO5  - Motor dedo índice
#define MOTOR2 D0  // GPIO14 - Motor dedo medio
#define MOTOR3 D7  // GPIO12 - Motor dedo anular
#define MOTOR4 D6  // GPIO13 - Motor dedo meñique

//  --- BOTÓN DE CONTROL --- (usa pin seguro)
#define BUTTON D5  // GPIO16 - Botón multifunción (Inicio/Pausa/Stop) (a gnd cuando se presiona)

// LEDs indicadores de progreso del tratamiento (2 horas dividida en 3 segmentos de 40 min)
#define LED1 D2    // GPIO4  - LED 1:  LED 1: Se enciende a los 40 min
#define LED2 D3    // GPIO0  - LED 2: Se enciende a los 80 min  ⚠️ puede interferir (ver abajo)
#define LED3 D4    // GPIO2  - LED 3: Se enciende a los 120 min (FIN) (LED_BUILTIN)

// --- LED DE ESTADO OPERATIVO ---
#define LED_STATUS D8  // GPIO15 - Parpadea mientras el tratamiento está activo

// ========================================================================
// CONSTANTES DEL PROTOCOLO vCR (Valores respaldados por investigación)
// ========================================================================

// Frecuencia de vibración objetivo: 250 Hz
// Período = 1/250Hz = 4000 microsegundos
// Ciclo de trabajo 50%: 2000µs ON + 2000µs OFF
#define VIBRATION_FREQUENCY_HZ 250
#define PULSE_ON_TIME_US 2000      // Tiempo que el motor está encendido
#define PULSE_OFF_TIME_US 2000     // Tiempo que el motor está apagado
#define PULSES_PER_BURST 97        // Número de pulsos por ráfaga de vibración

// Jitter entre estímulos (variación aleatoria ±23.5% del promedio)
// Promedio: 66.666 ms → Rango: 51 ms a 82.332 ms
#define JITTER_MIN_US 51000        // Jitter mínimo: 51 milisegundos
#define JITTER_MAX_US 82332        // Jitter máximo: 82.332 milisegundos

// Pausa larga después de 3 secuencias completas vCR
// Esta pausa es CRÍTICA para el efecto terapéutico
#define LONG_PAUSE_US 799992       // ~800 milisegundos
#define LONG_PAUSE_MS 1500         // 1.5 segundos adicionales

// Duración total del tratamiento: 2 HORAS (protocolo Stanford)
#define TREATMENT_DURATION_HOURS 2
#define TREATMENT_DURATION_MS (TREATMENT_DURATION_HOURS * 60UL * 60UL * 1000UL)

// Tiempos para encendido progresivo de LEDs (cada 40 minutos)
#define LED1_TIME_MS (40UL * 60UL * 1000UL)   // 40 minutos
#define LED2_TIME_MS (80UL * 60UL * 1000UL)   // 80 minutos
#define LED3_TIME_MS (120UL * 60UL * 1000UL)  // 120 minutos (2 horas)

// Debounce del botón (evita lecturas múltiples por rebote mecánico)
#define DEBOUNCE_DELAY_MS 50

// Parpadeo del LED de estado (indica operación activa)
#define STATUS_LED_BLINK_MS 1000   // Parpadea cada 1 segundo

// ========================================================================
// VARIABLES GLOBALES
// ========================================================================

// --- CONTROL DE ESTADO DEL SISTEMA ---
enum SystemState {
  IDLE,           // Sistema en reposo, esperando inicio
  RUNNING,        // Tratamiento en ejecución
  PAUSED,         // Tratamiento pausado por el usuario
  COMPLETED,      // Tratamiento completado (2 horas)
 // TEST_MODE       // Modo de prueba (mantener botón 5 seg al inicio)
};

SystemState currentState = IDLE;

// --- VARIABLES DE TIEMPO ---
unsigned long treatmentStartTime = 0;     // Momento de inicio del tratamiento
unsigned long pauseStartTime = 0;         // Momento de inicio de pausa
unsigned long totalPausedTime = 0;        // Tiempo total acumulado en pausa
unsigned long lastButtonCheck = 0;        // Última verificación del botón (debounce)
unsigned long lastStatusBlink = 0;        // Última vez que parpadeó LED de estado
bool statusLedState = false;              // Estado actual del LED de estado

// --- VARIABLES DE SECUENCIA vCR ---
int fingerSequence[] = { 0, 1, 2, 3 };    // Orden aleatorio de dedos (0=MOTOR1, 3=MOTOR4)
int sequenceIndex = 0;                    // Índice actual en la secuencia (0-3)
int vcrCycleCount = 0;                    // Contador de ciclos vCR (0-2)
int activeMotor1 = 0;                     // Primer motor activo en este ciclo
int activeMotor2 = 0;                     // Segundo motor activo en este ciclo

// --- VARIABLES DE JITTER ---
unsigned long interStimulusJitter = 0;    // Jitter individual para próxima pausa
unsigned long cumulativeJitter = 0;       // Acumulación de jitter para compensación

// --- CONTADOR DE SESIONES (para futuro uso con EEPROM) ---
// int dailySessions = 0;  // Descomenta si implementas memoria persistente

// ========================================================================
// DECLARACIÓN DE FUNCIONES
// ========================================================================

void initializeSystem();
void waitForButtonPress();
void handleButtonPress();
bool isButtonPressed();
void startTreatment();
void pauseTreatment();
void resumeTreatment();
void completeTreatment();
void runTreatmentCycle();
void generateVibroBurst(int motor1, int motor2);
void selectNextFingerPair();
void shuffleFingerSequence();
void updateProgressLEDs();
void updateStatusLED();
void blinkAllLEDs(int times, int delayMs);
//void testMode();
unsigned long getElapsedTreatmentTime();
void printStatusToSerial();
String getStateName(SystemState state);

// ========================================================================
// SETUP: Inicialización del sistema
// ========================================================================

void setup() {
  // Inicializar comunicación serial para debug (opcional)
  Serial.begin(115200);
  Serial.println("\n========================================");
  Serial.println("GUANTE TERAPÉUTICO PARKINSON vCR 2.0");
  Serial.println("========================================\n");
  
  initializeSystem();
  
  // Indicar que el sistema está listo
  blinkAllLEDs(3, 200);  // Parpadear 3 veces = Sistema listo
  Serial.println("Sistema listo. Presione el botón para iniciar.");
  Serial.println("Mantenga presionado 5 seg para modo PRUEBA.\n");
}

// ========================================================================
// LOOP PRINCIPAL: Máquina de estados
// ========================================================================

void loop() {
  // Manejar eventos del botón (con debounce)
  if (millis() - lastButtonCheck > DEBOUNCE_DELAY_MS) {
    handleButtonPress();
    lastButtonCheck = millis();
  }
  
  // Ejecutar acciones según el estado actual
  switch (currentState) {
    case IDLE:
      // Esperando que el usuario presione el botón
      updateStatusLED();  // Parpadeo lento = esperando
      break;
      
    case RUNNING:
      // Ejecutar un ciclo completo de tratamiento
      runTreatmentCycle();// <--- Esta es la prioridad (baja latencia)
      updateProgressLEDs();
      updateStatusLED();
      printStatusToSerial(); // <--- me imprime el tiempo restante de tratamiento
      
      // Verificar si se completó el tratamiento (2 horas)
      if (getElapsedTreatmentTime() >= TREATMENT_DURATION_MS) {
        completeTreatment();
      }
      break;
      
    case PAUSED:
      // Tratamiento pausado - solo parpadear LED de estado
      updateStatusLED();
      break;
      
    case COMPLETED:
      // Tratamiento completado - esperar reinicio
      // Los LEDs ya están todos encendidos
      break;
    /*  
    case TEST_MODE:
      // Modo de prueba ya se ejecutó en setup, volver a IDLE
      currentState = IDLE;
      break;
    */
  }
}

// ========================================================================
// FUNCIONES DE INICIALIZACIÓN
// ========================================================================

/**
 * Configura todos los pines y variables del sistema
 */
void initializeSystem() {
  // Configurar pines de motores como salida (inicialmente apagados)
  pinMode(MOTOR1, OUTPUT);
  pinMode(MOTOR2, OUTPUT);
  pinMode(MOTOR3, OUTPUT);
  pinMode(MOTOR4, OUTPUT);
  digitalWrite(MOTOR1, LOW);
  digitalWrite(MOTOR2, LOW);
  digitalWrite(MOTOR3, LOW);
  digitalWrite(MOTOR4, LOW);
  
  // Configurar LEDs de progreso como salida (inicialmente prendidos)
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  pinMode(LED3, OUTPUT);
// Iniciar LEDs de progreso en ALTO (HIGH)
  digitalWrite(LED1, HIGH);
  digitalWrite(LED2, HIGH);
  digitalWrite(LED3, HIGH);
  
  // Configurar LED de estado como salida
  pinMode(LED_STATUS, OUTPUT);
  digitalWrite(LED_STATUS, LOW);
  
  // Configurar botón con resistencia pull-up interna
  // El botón conecta el pin a GND cuando se presiona
  pinMode(BUTTON, INPUT_PULLUP);
  
  // Inicializar generador de números aleatorios
  // Usa ruido analógico como semilla para mejor aleatoriedad
  randomSeed(analogRead(A0));
  
  // Generar primera secuencia aleatoria de dedos
  shuffleFingerSequence();
  
  // Verificar si se mantiene presionado el botón al iniciar (MODO PRUEBA)
  //if (isButtonPressed()) {
  //  unsigned long pressStart = millis();
  //  while (isButtonPressed() && (millis() - pressStart < 5000)) {
  //    delay(10);
  //  }
  //  if (millis() - pressStart >= 5000) {
  //    testMode();
  //  }
  //}
}

// ========================================================================
// FUNCIONES DE CONTROL DE ESTADO
// ========================================================================

/**
 * Verifica si el botón está presionado (con lógica invertida por pull-up)
 */
bool isButtonPressed() {
  return digitalRead(BUTTON) == LOW;
}

/**
 * Maneja las pulsaciones del botón según el estado actual
 * - IDLE: Inicia el tratamiento
 * - RUNNING: Pausa el tratamiento
 * - PAUSED: Resume el tratamiento
 * - COMPLETED: Reinicia el sistema
 */
 
void handleButtonPress() {
  static bool lastButtonState = HIGH;
  bool currentButtonState = digitalRead(BUTTON);
  
  // Detectar transición de HIGH a LOW (botón recién presionado)
  if (lastButtonState == HIGH && currentButtonState == LOW) {
    switch (currentState) {
      case IDLE:
        startTreatment();
        break;
      case RUNNING:
        pauseTreatment();
        break;
      case PAUSED:
        resumeTreatment();
        break;
      case COMPLETED:
        // Reiniciar el sistema
        Serial.println("\n=== REINICIANDO SISTEMA ===");
        currentState = IDLE;
        treatmentStartTime = 0;
        totalPausedTime = 0;
        sequenceIndex = 0;
        vcrCycleCount = 0;
        digitalWrite(LED1, LOW);
        digitalWrite(LED2, LOW);
        digitalWrite(LED3, LOW);
        blinkAllLEDs(2, 300);
        Serial.println("Sistema reiniciado. Listo para nueva sesión.\n");
        break;
    }
  }
  
  lastButtonState = currentButtonState;
}

/**
 * Inicia el tratamiento
 */
void startTreatment() {
  Serial.println("\n=== INICIANDO TRATAMIENTO ===");
  Serial.println("Duración: 2 horas");
  Serial.println("Presione el botón para PAUSAR en cualquier momento.\n");
  
  treatmentStartTime = millis();
  totalPausedTime = 0;
  currentState = RUNNING;
  
  // Feedback visual: parpadear LED de estado rápidamente
  for (int i = 0; i < 5; i++) {
    digitalWrite(LED_STATUS, HIGH);
    delay(100);
    digitalWrite(LED_STATUS, LOW);
    delay(100);
  }
}

/**
 * Pausa el tratamiento
 */
void pauseTreatment() {
  Serial.println("\n=== TRATAMIENTO PAUSADO ===");
  Serial.println("Presione el botón para CONTINUAR.\n");
  
  pauseStartTime = millis();
  currentState = PAUSED;
  
  // Apagar todos los motores
  digitalWrite(MOTOR1, LOW);
  digitalWrite(MOTOR2, LOW);
  digitalWrite(MOTOR3, LOW);
  digitalWrite(MOTOR4, LOW);
  
  // Feedback visual: parpadear todos los LEDs
  blinkAllLEDs(2, 200);
}

/**
 * Resume el tratamiento después de una pausa
 */
void resumeTreatment() {
  Serial.println("\n=== REANUDANDO TRATAMIENTO ===\n");
  
  // Acumular el tiempo que estuvo en pausa
  totalPausedTime += (millis() - pauseStartTime);
  currentState = RUNNING;
  
  // Feedback visual
  blinkAllLEDs(2, 200);
}

/**
 * Completa el tratamiento (2 horas alcanzadas)
 */
void completeTreatment() {
  Serial.println("\n========================================");
  Serial.println("¡TRATAMIENTO COMPLETADO!");
  Serial.println("Duración: 2 horas");
  Serial.println("========================================");
  Serial.println("\nPresione el botón para iniciar nueva sesión.\n");
  
  currentState = COMPLETED;
  
  // Apagar todos los motores
  digitalWrite(MOTOR1, LOW);
  digitalWrite(MOTOR2, LOW);
  digitalWrite(MOTOR3, LOW);
  digitalWrite(MOTOR4, LOW);
  
  // Encender todos los LEDs de progreso
  digitalWrite(LED1, HIGH);
  digitalWrite(LED2, HIGH);
  digitalWrite(LED3, HIGH);
  
  // Secuencia de celebración: parpadear LEDs rápidamente
  for (int i = 0; i < 10; i++) {
    digitalWrite(LED_STATUS, HIGH);
    delay(100);
    digitalWrite(LED_STATUS, LOW);
    delay(100);
  }
  
  // Dejar LED de estado encendido permanentemente
  digitalWrite(LED_STATUS, LOW);
}

// ========================================================================
// FUNCIONES DE TRATAMIENTO vCR
// ========================================================================

/**
 * Ejecuta un ciclo completo de tratamiento vCR:
 * 1. Genera ráfaga de vibración (97 pulsos a 250 Hz)
 * 2. Aplica pausa con jitter aleatorio
 * 3. Avanza al siguiente par de dedos
 * 4. Después de 3 secuencias completas: pausa larga
 */
void runTreatmentCycle() {
  // FASE 1: Generar ráfaga de vibración en el par de dedos actual
  generateVibroBurst(activeMotor1, activeMotor2);
  
  // FASE 2: Avanzar en la secuencia
  sequenceIndex++;
  
  if (sequenceIndex >= 4) {
    // Completamos una secuencia de 4 dedos
    sequenceIndex = 0;
    shuffleFingerSequence();  // Generar nuevo orden aleatorio
    vcrCycleCount++;
    
    if (vcrCycleCount >= 3) {
      // Completamos 3 secuencias vCR (3 x 4 dedos = 12 activaciones)
      vcrCycleCount = 0;
      
      // PAUSA LARGA: Crucial para efecto terapéutico duradero
      // Permite que el cerebro "desaprenda" patrones sincrónicos
      if (cumulativeJitter <= LONG_PAUSE_US) {
        delayMicroseconds(LONG_PAUSE_US - cumulativeJitter);
        delay(LONG_PAUSE_MS);
      } else {
        // Compensar si el jitter acumulado excedió el nominal
        delayMicroseconds((LONG_PAUSE_MS * 1000UL) - (LONG_PAUSE_US - cumulativeJitter));
      }
      cumulativeJitter = 0;  // Resetear acumulación de jitter
    }
  }
  
  // FASE 3: Seleccionar próximo par de dedos
  selectNextFingerPair();
  
  // FASE 4: Aplicar jitter inter-estímulo (variación aleatoria ±23.5%)
  // Este jitter es FUNDAMENTAL para prevenir nueva sincronización neuronal
  interStimulusJitter = random(JITTER_MIN_US, JITTER_MAX_US);
  cumulativeJitter += interStimulusJitter;
  delayMicroseconds(interStimulusJitter);
}

/**
 * Genera una ráfaga de vibración a 250 Hz en dos motores simultáneamente
 * 
 * @param motor1 Pin del primer motor
 * @param motor2 Pin del segundo motor
 */
void generateVibroBurst(int motor1, int motor2) {
  for (int pulse = 0; pulse < PULSES_PER_BURST; pulse++) {
    // Encender ambos motores
    digitalWrite(motor1, HIGH);
    digitalWrite(motor2, HIGH);
    delayMicroseconds(PULSE_ON_TIME_US);
    
    // Apagar ambos motores
    digitalWrite(motor1, LOW);
    digitalWrite(motor2, LOW);
    delayMicroseconds(PULSE_OFF_TIME_US);
  }
}

/**
 * Selecciona el próximo par de dedos a estimular
 * Estrategia: activar dedos en pares opuestos para balance
 * - Par 0: MOTOR1 (índice) + MOTOR4 (meñique)
 * - Par 1: MOTOR2 (medio) + MOTOR3 (anular)
 * - Par 2: MOTOR3 (anular) + MOTOR2 (medio)
 * - Par 3: MOTOR4 (meñique) + MOTOR1 (índice)
 */
void selectNextFingerPair() {
  int fingerPair = fingerSequence[sequenceIndex];
  
  switch (fingerPair) {
    case 0:
      activeMotor1 = MOTOR1;  // Índice
      activeMotor2 = MOTOR4;  // Meñique
      break;
    case 1:
      activeMotor1 = MOTOR2;  // Medio
      activeMotor2 = MOTOR3;  // Anular
      break;
    case 2:
      activeMotor1 = MOTOR3;  // Anular
      activeMotor2 = MOTOR2;  // Medio
      break;
    case 3:
      activeMotor1 = MOTOR4;  // Meñique
      activeMotor2 = MOTOR1;  // Índice
      break;
  }
}

/**
 * Genera un nuevo orden aleatorio de la secuencia de dedos
 * Usa el algoritmo de Fisher-Yates para mezcla uniforme
 * Pasos del algoritmo
    * Inicialización: Comienza con una secuencia de elementos (por ejemplo, un array) que se desea mezclar. 
    * Iteración hacia atrás: Recorre la secuencia desde el último elemento hasta el primero. 
    * Generar índice aleatorio: En cada iteración con índice i, genera un número entero aleatorio j entre 0 y i (inclusive). 
    * Intercambio: Intercambia el elemento en la posición actual (i) con el elemento en la posición aleatoria j. 
    * Repetir: Continúa el proceso para el siguiente elemento (decrementando i) hasta llegar al primer elemento de la lista. 
    * Resultado: Cuando el bucle finaliza, la secuencia original estará completamente mezclada. 
 */
void shuffleFingerSequence() {
  for (int i = 0; i < 4; i++) {
    int randomIndex = random(0, 4);
    // Intercambiar valores
    int temp = fingerSequence[randomIndex];
    fingerSequence[randomIndex] = fingerSequence[i];
    fingerSequence[i] = temp;
  }
}

// ========================================================================
// FUNCIONES DE FEEDBACK VISUAL
// ========================================================================

/**
 * Actualiza los LEDs de progreso según el tiempo transcurrido
 * LED1: Se enciende a los 40 minutos
 * LED2: Se enciende a los 80 minutos
 * LED3: Se enciende a los 120 minutos (2 horas - fin)
 */
void updateProgressLEDs() {
  unsigned long elapsed = getElapsedTreatmentTime();
  
  // LED3 (Apagado a 40 minutos)
  digitalWrite(LED3, (elapsed < LED1_TIME_MS) ? HIGH : LOW);

  // LED2 (Apagado a 80 minutos)
  digitalWrite(LED2, (elapsed < LED2_TIME_MS) ? HIGH : LOW);

  // LED1 (Apagado a 120 minutos)
  digitalWrite(LED1, (elapsed < LED3_TIME_MS) ? HIGH : LOW);
}

/**
 * Parpadea el LED de estado para indicar operación activa
 * Parpadeo lento (1 Hz) durante RUNNING
 * Parpadeo rápido (4 Hz) durante PAUSED
 * Encendido constante durante IDLE
 */
void updateStatusLED() {
  unsigned long currentMillis = millis();
  unsigned long blinkInterval = STATUS_LED_BLINK_MS;
  
  if (currentState == PAUSED) {
    blinkInterval = 250;  // Parpadeo rápido en pausa
  }
  
  if (currentState == RUNNING || currentState == PAUSED) {
    if (currentMillis - lastStatusBlink >= blinkInterval) {
      statusLedState = !statusLedState;
      digitalWrite(LED_STATUS, statusLedState);
      lastStatusBlink = currentMillis;
    }
  } else if (currentState == IDLE) {
    // Parpadeo muy lento en espera
    if (currentMillis - lastStatusBlink >= 2000) {
      statusLedState = !statusLedState;
      digitalWrite(LED_STATUS, statusLedState);
      lastStatusBlink = currentMillis;
    }
  }
}

/**
 * Hace parpadear todos los LEDs de progreso
 * Útil para feedback de eventos (inicio, pausa, etc.)
 * 
 * @param times Número de parpadeos
 * @param delayMs Tiempo en milisegundos entre encendido/apagado
 */
void blinkAllLEDs(int times, int delayMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED1, HIGH);
    digitalWrite(LED2, HIGH);
    digitalWrite(LED3, HIGH);
    digitalWrite(LED_STATUS, HIGH);
    delay(delayMs);
    digitalWrite(LED1, LOW);
    digitalWrite(LED2, LOW);
    digitalWrite(LED3, LOW);
    digitalWrite(LED_STATUS, LOW);
    delay(delayMs);
  }
}

// ========================================================================
// FUNCIONES AUXILIARES
// ========================================================================

/**
 * Calcula el tiempo transcurrido de tratamiento (excluyendo pausas)
 * 
 * @return Tiempo en milisegundos
 */
unsigned long getElapsedTreatmentTime() {
  if (currentState == IDLE || treatmentStartTime == 0) {
    return 0;
  }
  
  unsigned long totalElapsed = millis() - treatmentStartTime;
  
  // Restar el tiempo que estuvo en pausa
  unsigned long pauseTime = totalPausedTime;
  if (currentState == PAUSED) {
    pauseTime += (millis() - pauseStartTime);
  }
  
  return totalElapsed - pauseTime;
}

/**
 * MODO DE PRUEBA: Activa cada motor secuencialmente
 * Útil para verificar que todos los motores funcionan correctamente
 * Se activa manteniendo presionado el botón durante 5 segundos al inicio
 */

/*void testMode() {
  Serial.println("\n=== MODO PRUEBA ACTIVADO ===");
  Serial.println("Probando cada motor secuencialmente...\n");
  
  currentState = TEST_MODE;
  
  // Encender todos los LEDs durante el modo prueba
  digitalWrite(LED1, HIGH);
  digitalWrite(LED2, HIGH);
  digitalWrite(LED3, HIGH);
  digitalWrite(LED_STATUS, HIGH);
  
  // Probar cada motor individualmente
  int motors[] = {MOTOR1, MOTOR2, MOTOR3, MOTOR4};
  String motorNames[] = {"ÍNDICE", "MEDIO", "ANULAR", "MEÑIQUE"};
  
  for (int i = 0; i < 4; i++) {
    Serial.print("Probando motor ");
    Serial.print(motorNames[i]);
    Serial.println("...");
    
    // Vibrar durante 2 segundos
    unsigned long testStart = millis();
    while (millis() - testStart < 2000) {
      digitalWrite(motors[i], HIGH);
      delayMicroseconds(PULSE_ON_TIME_US);
      digitalWrite(motors[i], LOW);
      delayMicroseconds(PULSE_OFF_TIME_US);
    }
    
    delay(500);  // Pausa entre motores
  }
  
  // Probar todos los motores simultáneamente
  Serial.println("\nProbando TODOS los motores simultáneamente...");
  unsigned long testStart = millis();
  while (millis() - testStart < 3000) {
    for (int i = 0; i < 4; i++) {
      digitalWrite(motors[i], HIGH);
    }
    delayMicroseconds(PULSE_ON_TIME_US);
    for (int i = 0; i < 4; i++) {
      digitalWrite(motors[i], LOW);
    }
    delayMicroseconds(PULSE_OFF_TIME_US);
  }
  
  // Apagar todos los LEDs
  digitalWrite(LED1, LOW);
  digitalWrite(LED2, LOW);
  digitalWrite(LED3, LOW);
  digitalWrite(LED_STATUS, LOW);
  
  Serial.println("\n=== PRUEBA COMPLETADA ===");
  Serial.println("Reinicie el dispositivo para uso normal.\n");
  
  // Parpadear para indicar fin de prueba
  blinkAllLEDs(5, 200);
}
*/

// ========================================================================
// FUNCIONES AUXILIARES DE MONITOREO
// ========================================================================

void printStatusToSerial() {
  static unsigned long lastSerialPrint = 0;
  const unsigned long printInterval = 2000; // Imprimir cada 2 segundos
  Serial.print("ESTADO ACTUAL: ");
  Serial.println(getStateName(currentState));

  if (currentState == RUNNING && millis() - lastSerialPrint >= printInterval) {
    
    // Calcular el tiempo transcurrido y restante
    unsigned long elapsedMs = getElapsedTreatmentTime();
    unsigned long remainingMs = TREATMENT_DURATION_MS - elapsedMs;
    
    // Conversión a formato H:M:S para facilitar la lectura
    unsigned long elapsedSec = elapsedMs / 1000UL;
    unsigned long remainingSec = remainingMs / 1000UL;
    
    unsigned int h = remainingSec / 3600;
    unsigned int m = (remainingSec % 3600) / 60;
    unsigned int s = remainingSec % 60;
    
    // ------------------------------------------------------------------------
    // SALIDA DE DATOS
    Serial.print("TIEMPO TOTAL TRANSCURRIDO: ");
    Serial.print(elapsedSec / 60 / 60);
    Serial.print("h ");
    Serial.print((elapsedSec / 60) % 60);
    Serial.print("m ");
    Serial.print(elapsedSec % 60);
    Serial.println("s");
    
    Serial.print("TIEMPO RESTANTE: ");
    Serial.print(h);
    Serial.print("h ");
    Serial.print(m);
    Serial.print("m ");
    Serial.print(s);
    Serial.println("s");
    
    Serial.print("Jitter Acumulado (µs): ");
    Serial.println(cumulativeJitter);
    Serial.println("----------------------------------------");
    // ------------------------------------------------------------------------
    
    lastSerialPrint = millis();
  }
}

String getStateName(SystemState state) {
  switch (state) {
    case IDLE: return "IDLE (Esperando Inicio)";
    case RUNNING: return "RUNNING (Tratamiento Activo)";
    case PAUSED: return "PAUSED (En Pausa)";
    case COMPLETED: return "COMPLETED (Finalizado)";
    case TEST_MODE: return "TEST_MODE (Prueba de Motores)";
    default: return "DESCONOCIDO";
  }
}
