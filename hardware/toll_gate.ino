#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// RFID Pins
#define SS_PIN 8
#define RST_PIN 9

// Servo Pin
#define SERVO_PIN 3

// RFID Object
MFRC522 rfid(SS_PIN, RST_PIN);

// Servo Object
Servo gateServo;

// LCD Object
LiquidCrystal_I2C lcd(0x27, 16, 2);

void setup() {
  Serial.begin(9600); // Must match BAUD_RATE in middleware.py

  // Start RFID
  SPI.begin();
  rfid.PCD_Init();

  // Start Servo
  gateServo.attach(SERVO_PIN);
  gateServo.write(0);

  // Start LCD
  lcd.init();
  lcd.backlight();
  
  resetScreen();
}

void loop() {
  // Wait for card
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }

  // 1. Send UID data to Python in the format "UID tag : XX XX XX XX"
  Serial.print("UID tag :");
  for (byte i = 0; i < rfid.uid.size; i++) {
    // Add leading 0 if hex value is less than 0x10 for proper formatting
    if (rfid.uid.uidByte[i] < 0x10) {
      Serial.print(" 0");
    } else {
      Serial.print(" ");
    }
    Serial.print(rfid.uid.uidByte[i], HEX);
  }
  Serial.println();

  // Display processing status on LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Processing...");
  lcd.setCursor(0, 1);
  lcd.print("Please wait");

  // 2. Wait for response from Python Middleware (1 = Granted, 0 = Denied)
  unsigned long startTime = millis();
  while (Serial.available() == 0) {
    if (millis() - startTime > 5000) { // 5-second timeout
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Server Timeout");
      delay(2000);
      resetScreen();
      // Stop RFID reading for this card
      rfid.PICC_HaltA();
      rfid.PCD_StopCrypto1();
      return;
    }
  }

  // Read command from Python
  char response = Serial.read();

  // Clear leftover data in Serial Buffer
  while(Serial.available() > 0) {
    Serial.read();
  }

  // 3. Control Gate and LCD based on Database response
  lcd.clear();
  if (response == '1') {
    // ACCESS GRANTED (Sufficient funds)
    lcd.setCursor(0, 0);
    lcd.print("Access Granted");
    lcd.setCursor(0, 1);
    lcd.print("Safe Journey!");
    
    gateServo.write(90); // Open gate
    delay(3000);         // Keep open for 3 seconds
    gateServo.write(0);  // Close gate
  } 
  else if (response == '0') {
    // ACCESS DENIED (Insufficient funds or unregistered card)
    lcd.setCursor(0, 0);
    lcd.print("Access Denied");
    lcd.setCursor(0, 1);
    lcd.print("Check Balance");
    delay(3000);
  }

  // Return to default screen
  resetScreen();

  // Stop RFID
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

// Function to set default screen
void resetScreen() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SMART TOLL");
  lcd.setCursor(0, 1);
  lcd.print("Scan Card");
}