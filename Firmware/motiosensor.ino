// --- INCLUSIÓN DE LIBRERÍAS ---
#include "I2Cdev.h"
#include "MPU6050_6Axis_MotionApps20.h"
#include <Wire.h>
#include <SPI.h>
#include <SD.h> 
#include <ESP8266WiFi.h>                 // Conexión WiFi para ESP8266
#include <WiFiUdp.h>                     // Envío de datos UDP

// --- OBJETO MPU6050 ---
MPU6050 mpu;

// --- DEFINICIONES ---
#define LED_CALIBRACION 2 //D4
#define LED_SD 0 //D3
#define INTERRUPT_PIN 15 //(D8)
#define CS_PIN 16 // (D0)
#define BLINK_INTERVAL 500 // Intervalo de parpadeo en milisegundos

// --- CONFIGURACIÓN DEL ACCESS POINT ---
const char* ap_ssid = "WemosTest";     // Nombre del WiFi que creará el Wemos
const char* ap_password = "12345678";  // Contraseña mínima 8 caracteres
const unsigned int udpPort = 4210;     // Puerto UDP
const IPAddress clientIP(192, 168, 4, 2); // IP del receptor en el Access Point (por defecto .2)
WiFiUDP udp;

// --- VARIABLES DE CONTROL ---
float ypr[3];
Quaternion q;
VectorInt16 aa, aaReal;
VectorFloat gravity;

bool dmpOK = false;
bool sensorOK = false;
uint16_t packetSize;
uint8_t FIFOBuffer[64];
uint8_t MPUIntStatus;
uint8_t devStatus;
uint16_t FIFOCount;

File dataFile;
volatile bool MPUInterrupt = false;
bool sd_presente = false; 
bool ap_iniciado = false; 
bool wifi_habilitado = false;

// Estado de la operación para controlar el LED_SD
enum OperacionState {
  STATE_OK_SD,        // SD funciona, WiFi apagado, LED apagado
  STATE_FALLBACK_WIFI, // SD falló, WiFi funciona, LED encendido (fijo)
  STATE_FAIL_TOTAL     // SD y WiFi fallaron, LED titilando
};

OperacionState estado_operacion;
unsigned long lastBlinkTime = 0; 
uint8_t fileNumber = 0; // Contador para el nombre del archivo

// Función para generar un nuevo nombre de archivo incremental (DATOXX.CSV)
String getNewFileName() {
    fileNumber++; // Incrementar el número de archivo en cada llamada
    char filename[13]; // Espacio para "DATO00.CSV\0" (máximo DATO99.CSV)
    // snprintf es más seguro, pero sprintf está bien para un buffer pequeño
    sprintf(filename, "mpu_data%02d.CSV", fileNumber);
    return String(filename);
}


void ICACHE_RAM_ATTR DMPDataReady() {
  MPUInterrupt = true;
}

// Función para manejar el titileo del LED_SD
void handle_led_sd_blink() {
  if (estado_operacion != STATE_FAIL_TOTAL) return;
  
  unsigned long currentMillis = millis();
  if (currentMillis - lastBlinkTime >= BLINK_INTERVAL) {
    lastBlinkTime = currentMillis;
    // Cambiar el estado del LED (HIGH a LOW o LOW a HIGH)
    int ledState = digitalRead(LED_SD);
    digitalWrite(LED_SD, !ledState);
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(100000);
  pinMode(LED_CALIBRACION, OUTPUT);
  pinMode(LED_SD, OUTPUT);
  digitalWrite(LED_CALIBRACION, LOW);
  digitalWrite(LED_SD, LOW);

  // --- CONFIGURAR ACCESS POINT ---
  if (WiFi.softAP(ap_ssid, ap_password)) {
    ap_iniciado = true;
    IPAddress myIP = WiFi.softAPIP();
    Serial.print("Access Point iniciado. IP del Wemos: ");
    Serial.println(myIP);

    udp.begin(udpPort);
    Serial.print("UDP iniciado en puerto: ");
    Serial.println(udpPort);
  } else {
    ap_iniciado = false;
    Serial.println("❌ Error al iniciar el Access Point.");
  }

  // --- ESCANEO DE DISPOSITIVOS I2C ---
  byte error, address;
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("I2C device encontrado en dirección 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
    }
  }

  // --- INICIALIZAR MPU6050 ---
  mpu.initialize();
  if (mpu.testConnection()) {
    sensorOK = true;
  } else {
    Serial.println("Error: sensor no detectado.");
    return;
  }

  // --- CONFIGURAR DMP ---
  Serial.println(F("Inicializando DMP..."));
  yield();
  devStatus = mpu.dmpInitialize();
  yield();

  mpu.setRate(9);

  // Offsets
  mpu.setXGyroOffset(0);
  mpu.setYGyroOffset(0);
  mpu.setZGyroOffset(0);
  mpu.setXAccelOffset(0);
  mpu.setYAccelOffset(0);
  mpu.setZAccelOffset(0);

  if (devStatus == 0) {
    Serial.println(F("Calibrando sensor... ¡Mantené el MPU quieto!"));
    digitalWrite(LED_CALIBRACION, HIGH);

    mpu.CalibrateAccel(20);
    mpu.CalibrateGyro(20);

    digitalWrite(LED_CALIBRACION, LOW);
    Serial.println(F("✅ Calibración completa."));
    mpu.PrintActiveOffsets();

    Serial.println(F("Habilitando el DMP..."));
    mpu.setDMPEnabled(true);

    attachInterrupt(digitalPinToInterrupt(INTERRUPT_PIN), DMPDataReady, RISING);
    MPUIntStatus = mpu.getIntStatus();

    dmpOK = true;
    packetSize = mpu.dmpGetFIFOPacketSize();
    Serial.println(F("DMP listo! Esperando primera lectura..."));
  } else {
    Serial.print(F("Error al iniciar el DMP (código "));
    Serial.print(devStatus);
    Serial.println(F(")"));
  }

  // --- Inicializando tarjeta SD y CONFIGURACIÓN FINAL DEL ESTADO ---

  Serial.println("Inicializando tarjeta SD...");
  if (SD.begin(CS_PIN)) {
    // *** ESCENARIO 1: SD INICIALIZADA CORRECTAMENTE (PRIORIDAD) ***
    
    // Lógica para encontrar el primer nombre de archivo disponible (DATO01.CSV, DATO02.CSV...)
    String newFileName;
    // Se limita a 99 archivos por el formato DATOXX.CSV
    do {
      newFileName = getNewFileName();
    } while (SD.exists(newFileName) && fileNumber < 99); 

    if (fileNumber >= 99 && SD.exists(newFileName)) {
       Serial.println("❌ Advertencia: ¡Se alcanzó el límite de 99 archivos! No se puede crear un nuevo archivo.");
       // Si el contador llega a 99 y el archivo existe, forzamos un fallo lógico de SD.
       goto sd_fail_logic; 
    }
    
    Serial.print("✅ SD lista. Nuevo archivo: ");
    Serial.print(newFileName);
    Serial.println(". Deshabilitando WiFi.");
    
    sd_presente = true;
    wifi_habilitado = false; 
    digitalWrite(LED_SD, LOW); // LED apagado para modo diurno
    estado_operacion = STATE_OK_SD; 

    // Abrir el archivo encontrado
    dataFile = SD.open(newFileName.c_str(), FILE_WRITE);
    dataFile.println("Timestamp,Yaw,Pitch,Roll,Ax,Ay,Az");

  } else {
    sd_fail_logic: // Etiqueta para el caso de fallo de SD o de contador
    // *** ESCENARIO 2: SD FALLA (EVALUAR FALLBACK) ***
    Serial.println("❌ No se pudo inicializar la tarjeta SD.");
    sd_presente = false; 

    if (ap_iniciado) {
        // SD falló, pero el AP está OK. Usar WiFi y encender LED de advertencia.
        Serial.println("⚠️ SD ausente. Habilitando transmisión por WiFi.");
        wifi_habilitado = true;
        digitalWrite(LED_SD, HIGH); // LED encendido: Advertencia
        estado_operacion = STATE_FALLBACK_WIFI;
    } else {
        // SD falló Y el AP falló. Sin transmisión de datos. LED titilando.
        Serial.println("❌ SD y WiFi fallidos. Sin transmisión de datos. LED titilando.");
        wifi_habilitado = false;
        estado_operacion = STATE_FAIL_TOTAL;
    }
  }
}

void loop() {
  // *** LLAMADA PARA MANEJAR EL LED ***
  handle_led_sd_blink(); 
  
  if (!dmpOK || !MPUInterrupt) return;
  MPUInterrupt = false;

  if (mpu.getFIFOCount() < packetSize) return;
  mpu.getFIFOBytes(FIFOBuffer, packetSize);

  mpu.dmpGetQuaternion(&q, FIFOBuffer);
  mpu.dmpGetGravity(&gravity, &q);
  mpu.dmpGetYawPitchRoll(ypr, &q, &gravity);
  mpu.dmpGetAccel(&aa, FIFOBuffer);
  mpu.dmpGetLinearAccel(&aaReal, &aa, &gravity);

  unsigned long raw_timestamp = millis();
  // Funcion para formatear el tiempo
  String timestamp = formatTime(raw_timestamp);

  String data = String(timestamp) + "," +
                String(ypr[0] * 180 / M_PI) + "," +
                String(ypr[1] * 180 / M_PI) + "," +
                String(ypr[2] * 180 / M_PI) + "," +
                String(aaReal.x) + "," +
                String(aaReal.y) + "," +
                String(aaReal.z);

  Serial.println(data);
  
  // --- Enviar por SD (solo si está presente) ---
  if (sd_presente) {
    dataFile.println(data);
    
    static unsigned long lastFlush = 0;
    if (millis() - lastFlush > 1000) { // cada 1 segundo
      dataFile.flush();
      lastFlush = millis();
    }
  }

  // --- Enviar por WiFi (UDP) (solo si WiFi está habilitado) ---
  if (wifi_habilitado) {
    udp.beginPacket(clientIP, udpPort);
    udp.print(data);
    udp.endPacket();
  }
}

// Función para convertir milisegundos totales a formato HH:MM:SS.mmm
String formatTime(unsigned long ms) {
    unsigned long totalSeconds = ms / 1000;
    
    int msec = ms % 1000;
    int seconds = totalSeconds % 60;
    int minutes = (totalSeconds / 60) % 60;
    int hours = (totalSeconds / 3600); // Horas totales

    // Usamos sprintf para formatear con ceros a la izquierda (padding)
    char buffer[15]; // Suficiente espacio para HH:MM:SS.mmm y terminador null
    sprintf(buffer, "%02d:%02d:%02d.%03d", hours, minutes, seconds, msec);

    return String(buffer);
}