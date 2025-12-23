// --- INCLUSIÓN DE LIBRERÍAS ---
#include "I2Cdev.h"
#include "MPU6050_6Axis_MotionApps20.h"
#include <Wire.h>
#include <SPI.h>
#include <SD.h> 
#include <ESP8266WiFi.h>                 
#include <WiFiUdp.h>                     

// --- OBJETO MPU6050 ---
MPU6050 mpu;

// --- DEFINICIONES ---
#define LED_CALIBRACION 2 //D4
#define LED_SD 0          //D3

#define INTERRUPT_PIN 15  //(D8)
#define CS_PIN 16         //(D0)
#define BLINK_INTERVAL 500 
#define RETRY_INTERVAL 5000 

// --- CONFIGURACIÓN DEL ACCESS POINT ---
const char* ap_ssid = "WemosTest";     
const char* ap_password = "12345678";  
const unsigned int udpPort = 4210;     
const IPAddress clientIP(192, 168, 4, 2); 
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
unsigned long lastRetryTime = 0; 

// Estado de la operación
enum OperacionState {
  STATE_OK_SD,        
  STATE_FALLBACK_WIFI, 
  STATE_FAIL_TOTAL     
};

OperacionState estado_operacion;
unsigned long lastBlinkTime = 0; 
uint8_t fileNumber = 0; 

// --- PROTOTIPOS DE FUNCIONES ---
String formatTime(unsigned long ms);

String getNewFileName() {
    fileNumber++; 
    char filename[13]; 
    sprintf(filename, "mpu_data%02d.CSV", fileNumber);
    return String(filename);
}

void ICACHE_RAM_ATTR DMPDataReady() {
  MPUInterrupt = true;
}

// --- FUNCIÓN DE APERTURA DE ARCHIVO ---
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
  if (estado_operacion != STATE_FAIL_TOTAL) return;
  
  unsigned long currentMillis = millis();
  if (currentMillis - lastBlinkTime >= BLINK_INTERVAL) {
    lastBlinkTime = currentMillis;
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
    Serial.print("AP iniciado IP: "); Serial.println(myIP);
    udp.begin(udpPort);
  } else {
    ap_iniciado = false;
    Serial.println("❌ Error AP.");
  }

  // --- INICIALIZAR MPU6050 ---
  mpu.initialize();
  if (mpu.testConnection()) {
    sensorOK = true;
  } else {
    Serial.println("❌Error: sensor no detectado.");
    estado_operacion = STATE_FAIL_TOTAL;
    return;
  }

  // --- CONFIGURAR DMP ---
  Serial.println(F("Inicializando DMP..."));
  devStatus = mpu.dmpInitialize();

  mpu.setRate(9); 

  mpu.setXGyroOffset(0); mpu.setYGyroOffset(0); mpu.setZGyroOffset(0);
  mpu.setXAccelOffset(0); mpu.setYAccelOffset(0); mpu.setZAccelOffset(0);

  if (devStatus == 0) {
    Serial.println(F("Calibrando..."));
    digitalWrite(LED_CALIBRACION, HIGH);
    mpu.CalibrateAccel(20);
    mpu.CalibrateGyro(20);
    digitalWrite(LED_CALIBRACION, LOW);
    Serial.println(F("✅ Calibrado."));
    
    mpu.setDMPEnabled(true);
    attachInterrupt(digitalPinToInterrupt(INTERRUPT_PIN), DMPDataReady, RISING);
    MPUIntStatus = mpu.getIntStatus();
    dmpOK = true;
    packetSize = mpu.dmpGetFIFOPacketSize();
  } else {
    Serial.print(F("Error DMP: ")); Serial.println(devStatus);
    estado_operacion = STATE_FAIL_TOTAL;
    return;
  }

  // --- INICIALIZANDO TARJETA SD ---
  Serial.println("Inicializando SD...");
  if (SD.begin(CS_PIN)) {
    if (iniciarArchivoSD()) {
        sd_presente = true;
        wifi_habilitado = false; 
        digitalWrite(LED_SD, LOW); 
        estado_operacion = STATE_OK_SD; 
        Serial.println("✅ SD lista. WiFi desactivado.");
    } else {
        goto sd_fail_logic; 
    }
  } else {
    sd_fail_logic: 
    Serial.println("❌ Fallo SD.");
    sd_presente = false; 

    if (ap_iniciado) {
        Serial.println("⚠️ Usando WiFi.");
        wifi_habilitado = true;
        digitalWrite(LED_SD, HIGH); 
        estado_operacion = STATE_FALLBACK_WIFI;
    } else {
        Serial.println("❌ Fallo Total.");
        wifi_habilitado = false;
        estado_operacion = STATE_FAIL_TOTAL;
    }
  }
}

void loop() {
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

  String timestamp = formatTime(millis());
  String data = String(timestamp) + "," +
                String(ypr[0] * 180 / M_PI) + "," +
                String(ypr[1] * 180 / M_PI) + "," +
                String(ypr[2] * 180 / M_PI) + "," +
                String(aaReal.x) + "," +
                String(aaReal.y) + "," +
                String(aaReal.z);
  
  Serial.println(data); 

  // ============================================================
  // 1. INTENTO DE ESCRITURA EN SD
  // ============================================================
  if (sd_presente) {
    size_t escrito = dataFile.println(data);
    
    if (escrito == 0) {
        Serial.println("❌ SD desconectada.");
        sd_presente = false;
        dataFile.close(); 
        
        // TU LÓGICA CORRECTA: Apagar WiFi y marcar falla total
        wifi_habilitado = false; 
        estado_operacion = STATE_FAIL_TOTAL;

    } else {
        static unsigned long lastFlush = 0;
        if (millis() - lastFlush > 1000) { 
          dataFile.flush();
          lastFlush = millis();
        }
    }
  }

  // ============================================================
  // 2. INTENTO DE RECONEXIÓN
  // ============================================================
  if (!sd_presente && estado_operacion == STATE_FAIL_TOTAL && (millis() - lastRetryTime > RETRY_INTERVAL)) {
      lastRetryTime = millis();
      Serial.print("🔄 Reconectando SD... ");
      
      SD.end(); 
      digitalWrite(CS_PIN, HIGH);
      delay(50); 

      if (SD.begin(CS_PIN)) {
          Serial.println("Hardware OK. Montando FS...");
          delay(100); 

          if (iniciarArchivoSD()) {
              sd_presente = true;
              wifi_habilitado = false; 
              
              digitalWrite(LED_SD, LOW); 
              estado_operacion = STATE_OK_SD;

              // -----------------------------------------------------
              // 🔥 EL FIX PARA EL RUIDO (TAMBIÉN FALTABA) 🔥
              // -----------------------------------------------------
              Serial.println("♻️ Limpiando buffer...");
              mpu.resetFIFO();       
              MPUInterrupt = false;
              FIFOBuffer[0] = 0;    
              // -----------------------------------------------------

              Serial.println("✅ RECUPERADO.");
          } else {
               SD.end(); 
          }
      } else {
          Serial.println("❌ Falló Hardware.");
      }
  }

  // ============================================================
  // 3. ENVÍO POR WIFI
  // ============================================================
  if (wifi_habilitado) {
    udp.beginPacket(clientIP, udpPort);
    udp.print(data);
    udp.endPacket();
  }
}

// Función auxiliar
String formatTime(unsigned long ms) {
    unsigned long totalSeconds = ms / 1000;
    int msec = ms % 1000;
    int seconds = totalSeconds % 60;
    int minutes = (totalSeconds / 60) % 60;
    int hours = (totalSeconds / 3600); 

    char buffer[15]; 
    sprintf(buffer, "%02d:%02d:%02d.%03d", hours, minutes, seconds, msec);
    return String(buffer);
}