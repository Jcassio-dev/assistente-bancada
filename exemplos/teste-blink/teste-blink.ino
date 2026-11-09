// Pisca um LED no GPIO 2 e escreve o estado na serial.
const int PINO_LED = 2;
bool aceso = false;

void setup() {
  Serial.begin(115200);
  pinMode(PINO_LED, OUTPUT);
  Serial.println("teste-blink iniciado");
}

void loop() {
  aceso = !aceso;
  digitalWrite(PINO_LED, aceso ? HIGH : LOW);
  Serial.println(aceso ? "LED: ACESO" : "LED: APAGADO");
  delay(500);
}
