#ifndef RFID
#define RFID
#include "khaibao.h"

static inline void RF() {

  // KHÔNG delay – KHÔNG in linh tinh
  if (!rfid.PICC_IsNewCardPresent()) return;
  if (!rfid.PICC_ReadCardSerial()) return;

  // In UID khi CÓ THẺ
  SerialBT.print("UID = ");
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) SerialBT.print("0");
    SerialBT.print(rfid.uid.uidByte[i], HEX);
    SerialBT.print(" ");
  }
  SerialBT.println();

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}
#endif
