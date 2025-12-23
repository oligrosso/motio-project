#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WebSocketsClient.h> 
#include <Wire.h>
#include "I2Cdev.h"
#include "MPU6050_6Axis_MotionApps20.h"
#include <SPI.h>
#include <SD.h>
#include <time.h> // Para la hora real

// --- DEFINICIONES ---
#define LED_CALIBRACION 2 // D4 (LED azul interno - active LOW)
#define LED_SD 0          // D3 (LED rojo externo - active HIGH)
#define INTERRUPT_PIN 15  // D8
#define CS_PIN 16         // D0
#define BLINK_INTERVAL 500 
#define RETRY_INTERVAL 5000 

// --- CREDENCIALES WIFI ---
const char* ssid = "iPhone de Jazmín";  // ⚠️ CAMBIAR: nombre de tu red WiFi
const char* password = "jazmin123";  

// --- RENDER (EIO=4) ---
const char* host = "motiometrics-backend.onrender.com";
const int port = 443; 
const uint8_t fingerprint[] = {
  0xA8, 0xEE, 0x46, 0x11, 0x10, 0x0C, 0x0E, 0x7D, 0x4E, 0x9D, 
  0x25, 0xEB, 0x63, 0x50, 0x68, 0x30, 0x45, 0x91, 0x6B, 0x28
}; // seguridad para conexiones HTTPS/SSL

// --- OBJETOS ---
WebSocketsClient webSocket;
MPU6050 mpu;
File dataFile;

// --- VARIABLES DE CONTROL ---
uint8_t FIFOBuffer[64];
Quaternion q; 
VectorFloat gravity;
float ypr[3];  // Yaw, Pitch, Roll - los ángulos de inclinación
VectorInt16 aa, aaReal; // aceleración lineal sin gravedad
uint16_t packetSize;
bool dmpOK = false;

// Variables de Tara
float initialYaw = 0; // La primera lectura válida se guarda como "punto cero" (initialYaw), así las mediciones empiezan desde 0.
bool initialYawSet = false;
int warmup_counter = 0;

// CONTROL DE FLUJO WIFI (DECIMACIÓN): Sirve para que el ESP8266 no intente enviar datos más rápido de lo que el WiFi o el servidor pueden procesar.
unsigned long lastWifiSend = 0;// Guarda el momento exacto (en milisegundos) en el que se envió el último paquete con éxito.
const int WIFI_INTERVAL = 40; // ~25fps Frecuencia de Transmisión: Si cambias 40 por 20, enviarás el doble de datos (50 veces por segundo).

// Variables SD y Estados
bool sd_presente = false;
bool wifi_habilitado = false;
bool isConnected = false; 
uint8_t fileNumber = 0;
unsigned long lastBlinkTime = 0;
unsigned long lastRetryTime = 0;
unsigned long lastFlush = 0;

// Enum
enum OperacionState {
  STATE_OK_SD,        
  STATE_FALLBACK_WIFI, 
  STATE_FAIL_TOTAL     
};
OperacionState estado_operacion = STATE_FAIL_TOTAL; // Valor por defecto seguro

// --- FUNCIONES AUXILIARES ---

String getNewFileName() {
    fileNumber++; 
    char filename[13]; 
    sprintf(filename, "mpu_data%02d.CSV", fileNumber);
    return String(filename);
}

bool iniciarArchivoSD() {
    String newFileName;
    int intentos = 0;
    do {
      newFileName = getNewFileName();
      intentos++;
    } while (SD.exists(newFileName) && fileNumber < 99 && intentos < 100);

    if (fileNumber >= 99 && SD.exists(newFileName)) {
       Serial.println("❌ Límite de archivos alcanzado.");
       return false;
    }

    dataFile = SD.open(newFileName.c_str(), FILE_WRITE);
    if (dataFile) {
      dataFile.println("Timestamp,Yaw,Pitch,Roll,Ax,Ay,Az");
      dataFile.flush(); 
      Serial.print("✅ Archivo creado: "); Serial.println(newFileName);
      return true;
    } else {
      Serial.print("❌ Error: No se pudo crear "); Serial.println(newFileName);
      return false;
    }
}

void handle_led_sd_blink() {
  if (estado_operacion == STATE_FAIL_TOTAL) {
    unsigned long currentMillis = millis();
    if (currentMillis - lastBlinkTime >= BLINK_INTERVAL) {
      lastBlinkTime = currentMillis;
      digitalWrite(LED_SD, !digitalRead(LED_SD)); // Toggle
    }
  }
  // En otros estados el LED se controla manualmente
}

String formatTime(unsigned long ms) {
  time_t now = time(nullptr);
  struct tm* timeinfo = localtime(&now);
  
  if (timeinfo->tm_year > 120) { // Hora de internet disponible
      char buffer[20];
      int msec = ms % 1000;
      sprintf(buffer, "%02d:%02d:%02d.%03d", timeinfo->tm_hour, timeinfo->tm_min, timeinfo->tm_sec, msec);
      return String(buffer);
  } 
  
  // Fallback tiempo relativo
  unsigned long totalSeconds = ms / 1000;
  int msec = ms % 1000;
  int seconds = totalSeconds % 60;
  int minutes = (totalSeconds / 60) % 60;
  int hours = (totalSeconds / 3600);
  char buffer[15];
  sprintf(buffer, "%02d:%02d:%02d.%03d", hours, minutes, seconds, msec);
  return String(buffer);
}

// --- EVENTOS WEBSOCKET ---
void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("[WS] Desconectado!");
      isConnected = false;
      break;
    case WStype_CONNECTED:
      Serial.println("[WS] Conectado! Esperando handshake...");
      break;
    case WStype_TEXT:
      char msgType = (char)payload[0];
      if(msgType == '0') {
        Serial.println("[EIO4] Sesión Abierta.");
        webSocket.sendTXT("40"); 
        isConnected = true;
      }
      else if(msgType == '4') {
        if((char)payload[1] == '0') Serial.println("[IO] ✅ CONEXIÓN OK");
      }
      else if(msgType == '2') {
        webSocket.sendTXT("3"); // PONG
      }
      break;
  }
}

// --- SETUP ---
void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);

  // --- LEDS SETUP ---
  pinMode(LED_CALIBRACION, OUTPUT);
  pinMode(LED_SD, OUTPUT);
  digitalWrite(LED_CALIBRACION, LOW);  // Apagado al inicio (active LOW)
  digitalWrite(LED_SD, LOW);            // Apagado al inicio

  // --- MPU SETUP ---
  Serial.println("Iniciando MPU...");
  mpu.initialize();
  
  if (mpu.testConnection()) {
    Serial.println("MPU conectado.");
  } else {
    Serial.println("❌ Error: sensor no detectado.");
    estado_operacion = STATE_FAIL_TOTAL;
    return;
  }

  Serial.println(F("Inicializando DMP..."));
  uint8_t devStatus = mpu.dmpInitialize();

  mpu.setXGyroOffset(0); mpu.setYGyroOffset(0); mpu.setZGyroOffset(0);
  mpu.setXAccelOffset(0); mpu.setYAccelOffset(0); mpu.setZAccelOffset(0);

  if (devStatus == 0) {
    Serial.println(F("Calibrando... (NO MOVER)"));
    digitalWrite(LED_CALIBRACION, HIGH);   // PRENDE LED azul
    
    mpu.CalibrateAccel(20);
    mpu.CalibrateGyro(20);
    mpu.PrintActiveOffsets();
    
    digitalWrite(LED_CALIBRACION, LOW);  // APAGA LED azul
    Serial.println(F("✅ Calibrado."));
    
    mpu.setRate(9); // La frecuencia interna del sensor (DMP Rate) 200Hz / (1 + 9) = 20Hz
    mpu.setDMPEnabled(true);
    packetSize = mpu.dmpGetFIFOPacketSize();
    dmpOK = true;
  } else {
    Serial.print(F("Error DMP: ")); Serial.println(devStatus);
    estado_operacion = STATE_FAIL_TOTAL;
  }

  // --- SD SETUP ---
  Serial.println("Iniciando SD...");
  if (SD.begin(CS_PIN)) {
    if (iniciarArchivoSD()) {
        sd_presente = true;
        wifi_habilitado = false; 
        digitalWrite(LED_SD, LOW);         // Apagado → SD OK
        estado_operacion = STATE_OK_SD; 
        WiFi.mode(WIFI_OFF); 
        Serial.println("✅ SD lista. WiFi desactivado.");
    } else {
        goto sd_fail_logic; 
    }
  } else {
    sd_fail_logic: 
    Serial.println("❌ Fallo SD.");
    sd_presente = false; 

    Serial.println("⚠️ Usando Fallback WiFi.");
    wifi_habilitado = true;
    digitalWrite(LED_SD, HIGH);            // PRENDE fijo → WiFi activo
    estado_operacion = STATE_FALLBACK_WIFI;

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
    Serial.print("Conectando WiFi");
    int contador = 0;
    while (WiFi.status() != WL_CONNECTED && contador < 30) { // 30 intentos de 0.5s = 15 seg
        delay(500);
        Serial.print(".");
        contador++;
    }

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\n❌ No se pudo conectar al WiFi. Pasando a modo Error.");
        estado_operacion = STATE_FAIL_TOTAL;
        return; // Sale del setup y el loop se encargará de intentar reconectar o avisar
    }
    Serial.println(" OK");

    configTime(-3 * 3600, 0, "pool.ntp.org", "time.nist.gov");

    webSocket.beginSSL(host, port, "/socket.io/?EIO=4&transport=websocket", fingerprint);
    webSocket.onEvent(webSocketEvent);
    webSocket.setExtraHeaders("Origin: https://motiometrics-backend.onrender.com");
    webSocket.setReconnectInterval(5000);
  }
}

// --- LOOP ---
void loop() {
  handle_led_sd_blink(); 

  if (wifi_habilitado) {
    webSocket.loop();
  }

  if (!dmpOK) return;

  if (mpu.dmpGetCurrentFIFOPacket(FIFOBuffer)) { // <--- Bloque A (20Hz)
    
    mpu.dmpGetQuaternion(&q, FIFOBuffer);
    mpu.dmpGetGravity(&gravity, &q);
    mpu.dmpGetYawPitchRoll(ypr, &q, &gravity);
    mpu.dmpGetAccel(&aa, FIFOBuffer);
    mpu.dmpGetLinearAccel(&aaReal, &aa, &gravity);

    if (warmup_counter < 500) {
        warmup_counter++;
        return;
    }
    if (!initialYawSet) {
        initialYaw = ypr[0];
        initialYawSet = true;
    }

    float yawCorrected = ypr[0] - initialYaw;
    if (yawCorrected < -M_PI) yawCorrected += 2 * M_PI;
    if (yawCorrected > M_PI) yawCorrected -= 2 * M_PI;

    float y_deg = yawCorrected * 180/M_PI;
    float p_deg = ypr[1] * 180/M_PI;
    float r_deg = ypr[2] * 180/M_PI;

    // --- MODO SD ---
    if (estado_operacion == STATE_OK_SD) {
        char csvLine[100];
        sprintf(csvLine, "%s,%.2f,%.2f,%.2f,%d,%d,%d", 
                formatTime(millis()).c_str(), y_deg, p_deg, r_deg, aaReal.x, aaReal.y, aaReal.z);
        
        size_t escrito = dataFile.println(csvLine);
        
        if (escrito == 0) {
           Serial.println("❌ SD desconectada.");
           sd_presente = false;
           dataFile.close();
           wifi_habilitado = false;
           estado_operacion = STATE_FAIL_TOTAL; 
        } else {
           if (millis() - lastFlush > 1000) { 
             dataFile.flush();
             lastFlush = millis();
           }
        }
    }
    // --- MODO WIFI ---
    else if (estado_operacion == STATE_FALLBACK_WIFI) {
        if (isConnected && (millis() - lastWifiSend > WIFI_INTERVAL)) { // <--- Bloque B (25Hz)
            lastWifiSend = millis();
            
            char jsonPayload[256];
            sprintf(jsonPayload, "42[\"message\",\"{\\\"y\\\":%.2f,\\\"p\\\":%.2f,\\\"r\\\":%.2f,\\\"ax\\\":%d,\\\"ay\\\":%d,\\\"az\\\":%d}\"]",
                    y_deg, p_deg, r_deg, aaReal.x, aaReal.y, aaReal.z);
            webSocket.sendTXT(jsonPayload);
        }
    }
  }

  // --- RECONEXIÓN SD ---
  if (!sd_presente && estado_operacion == STATE_FAIL_TOTAL && (millis() - lastRetryTime > RETRY_INTERVAL)) {
      lastRetryTime = millis();
      Serial.print("🔄 Reconectando SD... ");
      SD.end(); 
      digitalWrite(CS_PIN, HIGH);
      delay(50); 
      if (SD.begin(CS_PIN)) {
          delay(100); 
          if (iniciarArchivoSD()) {
              sd_presente = true;
              wifi_habilitado = false; 
              WiFi.mode(WIFI_OFF); 
              digitalWrite(LED_SD, LOW);     // Apaga → volvió a SD
              estado_operacion = STATE_OK_SD;
              
              mpu.resetFIFO();        
              warmup_counter = 0;
              initialYawSet = false;
              
              Serial.println("✅ RECUPERADO.");
          } else { SD.end(); }
      } else { Serial.println("❌ Falló Hardware."); }
  }
}