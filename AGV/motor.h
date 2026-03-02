#ifndef motor
#define motor
#include "khaibao.h"

static inline void motores(int pwmA, int pwmB) {
  pwmA = constrain(pwmA, -255, 255);
  pwmB = constrain(pwmB, -255, 255);
  // Motor phải
  if (pwmA > 0) {
    digitalWrite(AIN1, HIGH);
    digitalWrite(AIN2, LOW);
  } else if (pwmA < 0) {
    digitalWrite(AIN1, LOW);
    digitalWrite(AIN2, HIGH);
  } else {
    digitalWrite(AIN1, LOW);
    digitalWrite(AIN2, LOW);
  }
  // Motor trái
  if (pwmB > 0) {
    digitalWrite(BIN1, HIGH);
    digitalWrite(BIN2, LOW);
  } else if (pwmB < 0) {
    digitalWrite(BIN1, LOW);
    digitalWrite(BIN2, HIGH);
  } else {
    digitalWrite(BIN1, LOW);
    digitalWrite(BIN2, LOW);
  }
  analogWrite(PWMA, abs(pwmA));
  analogWrite(PWMB, abs(pwmB));
}
/* =====================================================
   ENCODER – X1 (2 INTERRUPT, ỔN ĐỊNH)
   ===================================================== */

void motoresStop(){
  digitalWrite(AIN1, HIGH);
  digitalWrite(AIN2, HIGH);
  digitalWrite(BIN1, HIGH);
  digitalWrite(BIN2, HIGH);
  analogWrite(PWMA, 255);
  analogWrite(PWMB, 255);
}

volatile int32_t countA = 0;   // bánh phải
volatile int32_t countB = 0;   // bánh trái

void IRAM_ATTR readEncA() {
  if (digitalRead(ENCA_B)) countA++;
  else countA--;
}

void IRAM_ATTR readEncB() {
  if (digitalRead(ENCB_B)) countB++;
  else countB--;
}

static inline void encoderInit() {
  pinMode(ENCA_A, INPUT_PULLUP);
  pinMode(ENCA_B, INPUT_PULLUP);
  pinMode(ENCB_A, INPUT_PULLUP);
  pinMode(ENCB_B, INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(ENCA_A), readEncA, RISING);
  attachInterrupt(digitalPinToInterrupt(ENCB_A), readEncB, RISING);

  countA = 0;
  countB = 0;
}
void updateHeading(char cmd) {
  if (cmd == 'L')
    heading = (heading=='N')?'W':(heading=='W')?'S':(heading=='S')?'E':'N';
  else if (cmd == 'R')
    heading = (heading=='N')?'E':(heading=='E')?'S':(heading=='S')?'W':'N';
}
static inline void resetEncoder() {
  noInterrupts();
  countA = 0;
  countB = 0;
  interrupts();
}
void turnLeft() {
  int speed=200;
  int counts_90=1100;
  motores(0, 0);
  delay(10);

  resetEncoder();
  delay(5);

  // quay nhanh
  motores(-speed, speed);

  // hãm sớm 1 chút
  while (abs(countB) < counts_90 /2) {}

  motores(-80, 80);   // ⭐ speed MIN motor chạy được

  while (abs(countB) < counts_90) {}
  
    SerialBT.println("TURN LEFT");
    SerialBT.print("Pulse: ");
    SerialBT.println(abs(countB));
  motoresStop();
  delay(30);
  updateHeading('L');           // ⭐ cập nhật hướng
SerialBT.println("TURN,L");   // ⭐ gửi về PC

  resetEncoder();
}


/* =====================================================
   TURN RIGHT
   ===================================================== */
void turnRight() {
  int speed=200;
  int counts_90= 1200;
  motores(0, 0);
  delay(10);

  resetEncoder();
  delay(5);

  // quay nhanh
  motores(speed, -speed);

  // hãm sớm 1 chút
  while (abs(countA) < counts_90 /2) {}

  motores(80, -80);   // ⭐ speed MIN motor chạy được

  while (abs(countA) < counts_90) {}
  SerialBT.println("TURN RIGHT");
  SerialBT.print("Pulse: ");
  SerialBT.println(abs(countA));
  motoresStop();
  delay(30);
  updateHeading('R');
SerialBT.println("TURN,R");

  resetEncoder();
}



#endif