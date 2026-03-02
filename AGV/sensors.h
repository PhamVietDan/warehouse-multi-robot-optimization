#ifndef sensors
#define sensors

#include "khaibao.h"

struct CalibData {
  uint8_t  magic;
  uint16_t minVal[num];
  uint16_t maxVal[num];
  uint16_t threshold[num];
};

CalibData calib;
static inline void saveCalibEEPROM() {

  calib.magic = EEPROM_MAGIC;

  for (uint8_t i = 0; i < num; i++) {
    calib.minVal[i]    = ValueMin[i];
    calib.maxVal[i]    = ValueMax[i];
    calib.threshold[i] = threshold[i];
  }
  EEPROM.put(0, calib);
  EEPROM.commit();
  SerialBT.println("EEPROM SAVED");

}
static inline bool loadCalibEEPROM() {
  EEPROM.get(0, calib);
  if (calib.magic != EEPROM_MAGIC) {
    SerialBT.println("EEPROM INVALID");
    return false;
  }
  for (uint8_t i = 0; i < num; i++) {
    ValueMin[i]  = calib.minVal[i];
    ValueMax[i]  = calib.maxVal[i];
    threshold[i] = calib.threshold[i];
  }
  SerialBT.println("EEPROM LOADED");
  return true;
}

// ------------------- HÀM ĐỌC CẢM BIẾN -------------------
static inline void readSensor() {
  for (uint8_t i = 0; i < num; i++) {
    sensorValue[i] = analogRead(sensorPin[i]); // 0–4095 (12-bit)
  }
}
static inline void Test() {
  readSensor();   // đọc sensorValue[]

  for (uint8_t i = 0; i < num; i++) {
  
    SerialBT.print(sensorValue[i]);
    SerialBT.print("  ");
  }

  SerialBT.println();
}
static inline void calibrate() {
  for (uint8_t i = 0; i < num; i++) {
    ValueMin[i] = 4096;
    ValueMax[i] = 0;
  }
  unsigned long start = millis();
  while (millis() - start < 5000) {
    readSensor();
    for (uint8_t i = 0; i < num; i++) {
      uint16_t val = sensorValue[i];
      if (val < ValueMin[i]) ValueMin[i] = val;
      if (val > ValueMax[i]) ValueMax[i] = val;
    }
    delay(3);
  }
  for (uint8_t i = 0; i < num; i++) {
    threshold[i] =ValueMax[i] +300;
  }
  saveCalibEEPROM();
  // Debug
  SerialBT.println("CALIB DONE:");
  for (uint8_t i = 0; i < num; i++) {
    SerialBT.print("S"); SerialBT.print(i);
    SerialBT.print(" Min=");SerialBT.print(ValueMin[i]);
    SerialBT.print(" Max="); SerialBT.print(ValueMax[i]);
    SerialBT.print(" Th=");  SerialBT.println(threshold[i]);
  }
  delay(300);
}
static inline void readLine() {
  sumSensor = 0;
  sumWeight = 0;

  readSensor();

  for (uint8_t i = 0; i < num; i++) {
    if (sensorValue[i] >  300)
      S[i] = 1;
    else
      S[i] = 0;

    sumSensor += S[i];
    sumWeight += S[i] * weightValue[i];

    Serial.print(S[i]);
    Serial.print(' ');
    SerialBT.print(S[i]);
    SerialBT.print(' ');
  }

  Serial.print("|||| Sensor: ");
  Serial.print(sumSensor);
  Serial.print(" Weight: ");
  Serial.println(sumWeight);

  SerialBT.print("|||| Sensor: ");
  SerialBT.print(sumSensor);
  SerialBT.print(" Weight: ");
  SerialBT.println(sumWeight);
}

static inline void updateLine() {
  sumSensor = 0;
  sumWeight = 0;

  readSensor();   // đọc sensorValue[]
  for (uint8_t i = 0; i < num; i++) {
    if (sensorValue[i] > 300)
      S[i] = 1;
    else
      S[i] = 0;
  sumSensor += S[i];
  sumWeight += S[i] * weightValue[i];
  }
}

static inline void printMINMAXTH() {
  Serial.println("=== EEPROM MIN / MAX / TH ===");
  SerialBT.println("=== EEPROM MIN / MAX / TH ===");

  for (uint8_t i = 0; i < num; i++) {
    Serial.print("S"); Serial.print(i);
    Serial.print("  min="); Serial.print(ValueMin[i]);
    Serial.print("  max="); Serial.print(ValueMax[i]);
    Serial.print("  th=");  Serial.println(threshold[i]);

    SerialBT.print("S"); SerialBT.print(i);
    SerialBT.print("  min="); SerialBT.print(ValueMin[i]);
    SerialBT.print("  max="); SerialBT.print(ValueMax[i]);
    SerialBT.print("  th=");  SerialBT.println(threshold[i]);
  }

  Serial.println("============================");
  SerialBT.println("============================");
}




#endif