void setup() {
  Serial.begin(115200);
  delay(2000);  // Espera a que Serial se estabilice
  Serial.println("Serial listo!");
}

void loop() {
  Serial.println("Test Serial...");
  delay(1000);
}