#include <EEPROM.h>
#include "motor.h"
#include "sensors.h"
#include "run.h"
#include "khaibao.h"
#include "RFID.h"

char control = 'S';


// ====== BLUETOOTH CONTROL ======
inline void modeBluetooth() {
  if (SerialBT.available()) {
    control = SerialBT.read();
  }

  if (control == 'S') {
    motores(0, 0);
    return;
  }

  switch (control) {
    case 'F': go(31); break;
    case 'L': turnLeft(); break;
    case 'R': turnRight(); break;
    case 'B': motores(0, 0); break;
  }
}


void setup() {
  pinMode(PWMA, OUTPUT);
  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);
  pinMode(STBY, OUTPUT);
  pinMode(BIN1, OUTPUT);
  pinMode(BIN2, OUTPUT);
  pinMode(PWMB, OUTPUT);
  digitalWrite(STBY, HIGH);

  encoderInit();

  Serial.begin(115200);
  SerialBT.begin("ESP32_ROBOT");

  Serial.println("STEP MODE READY");
}

void loop() {
  modeBluetooth();
}
/* ================== LOOP ================== */
// void loop() {
//   static bool running = false;
//   static int lastMode = -1;
//   /* ===== NHẬN LỆNH BLUETOOTH (KHÔNG WHILE) ===== */
//   if (SerialBT.available()) {
//     char cmd = SerialBT.read();
//     // bỏ ký tự xuống dòng
//     if (cmd != '\n' && cmd != '\r') {

//       Serial.print("CMD = ");
//       Serial.println(cmd);
//       SerialBT.print("CMD = ");
//       SerialBT.println(cmd);

//       // ===== ĐỔI MODE =====
//       if (cmd >= '0' && cmd <= '6') {
//         mode = cmd - '0';
//         running = false;

//         Serial.print("Mode = ");
//         Serial.println(mode);
//         SerialBT.print("Mode = ");
//         SerialBT.println(mode);
//       }

//       // ===== START / STOP =====
//       else if (cmd == 'K') {
//         running = !running;

//         Serial.print("Running = ");
//         Serial.println(running);
//         SerialBT.print("Running = ");
//         SerialBT.println(running);

//         if (running) {
//           startTime = millis();
//           startDone = false;
//           resetEncoder();
//         } else {
//           motores(0, 0);
//         }
//       }

//       // ===== RESET =====
//       else if (cmd == 'R') {
//         running = false;
//         motores(0, 0);
//         done = false;
//         Serial.println("RESET");
//         SerialBT.println("RESET");
//       }
//     }
//   }

//   /* ===== MODE CHANGE INFO ===== */
//   if (mode != lastMode) {
//     lastMode = mode;

//     Serial.print(">> MODE ACTIVE = ");
//     Serial.println(mode);
//     SerialBT.print(">> MODE ACTIVE = ");
//     SerialBT.println(mode);
//   }

//   /* ===== MODE 0: RUN PID ===== */
//   if (mode == 0 && running) {
//     if (!startDone && millis() - startTime < 1000) {
//       motores(0, 0);
//       return;
//     }
//     startDone = true;
//     updateLine();
//     PID();
//   }

//   /* ===== MODE 1: TEST SENSOR ===== */
//   else if (mode == 1 && running) {
//     Test();
//   }

//   /* ===== MODE 2: CALIB ===== */
//   else if (mode == 2 && running) {
//     // chạy motor
//     motores(100, 100);
//   // in encoder (KHÔNG reset)
//   SerialBT.print("LEFT = ");
//   SerialBT.print(countA);
//   SerialBT.print(" | RIGHT = ");
//   SerialBT.println(countB);
//   delay(100);
  
//   }
  

//   /* ===== MODE 3: READ LINE ===== */
//   else if (mode == 3 && running) {
//     readLine();
//   }
  

// else if (mode == 4 && running) {
//   if (millis() - lastRF > 60) {
//     RF();
//     lastRF = millis();
//   }
// }
// else if (mode == 5 && running ) {
//     // calibrate();
//     // calibrated = true;
//     // running = false;

//   if (!startDone && millis() - startTime < 1000) {
//     motores(0, 0);
//     return;
//   }
//   startDone = true;

//   if (!done) {
//     turnRight(200);   // quay đúng 1 lần
//     done = true;
//   }
//   }
//   else if (mode == 6 && running ) {
//     if (!startDone && millis() - startTime < 1000) {
//     motores(0, 0);
//     return;
//   }
//     startDone = true;
//     Running();   // quay đúng 1 lần
// }
// }