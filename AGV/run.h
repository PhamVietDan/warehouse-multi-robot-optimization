#ifndef run
#define run
#include"khaibao.h"
void sendStepRealtime() {
  long avgPulse = (abs(countA) + abs(countB)) / 2;

  if (abs(avgPulse - lastSendPulse) >= STEP_PULSE) {
    lastSendPulse = avgPulse;
    SerialBT.print("STEP,");
    SerialBT.println(heading);
  }
}
uint8_t State() {
  if (sumSensor == 0) return MATLINE;
  if (S[0]&&S[1]&&S[2]) return LEFT;
  if (S[4]&&S[3]&&S[2]) return RIGHT;
  if ((S[2]) && sumSensor >= 1 && sumSensor <= 3)
    return BAMLINE;

  if (sumSensor >= 5) return BAMLINE;

  
  return BAMLINE;
}

static inline void PID() {
  uint8_t state = State();
  // -------- NET DUT --------
  if (state == LEFT||state== RIGHT) {
      motores(baseSpeed, baseSpeed);
      return;
  }
  currPos = (float)sumWeight / sumSensor;
  int speed = baseSpeed;
  // -------- CUA --------
  if (state == LEFT) {
    lastTurn = -1;
  }
  if (state == RIGHT) {
    lastTurn = 1;
  }
  // -------- PID --------
    eCurr = cenPos - currPos;
    dE = eCurr - ePrev;
    eSum += eCurr;
    // eSum = constrain(eSum, -80, 80);
    u = Kp * eCurr + Kd * dE + Ki * eSum;
    int leftSpeed  = speed - u;
    int rightSpeed = speed + u;
    leftSpeed  = constrain(leftSpeed, -speedmax, speedmax);
    rightSpeed = constrain(rightSpeed,  -speedmax, speedmax);
    motores(leftSpeed, rightSpeed);
    ePrev = eCurr;
}
void go(int cm) {
  float pulse = (cm*4000)/22 ;
  eSum = 0;
  ePrev = 0;
  motores(0, 0);
  delay(10);
  resetEncoder();
  delay(5);
  // hãm sớm 1 chút
  while ((abs(countA)+abs(countB))/2 < pulse) {
  updateLine();
  PID();
  sendStepRealtime();   // ⭐ cập nhật realtime
}
  
    SerialBT.print("S=:  ");
    SerialBT.print(cm);
    SerialBT.println("cm ");

   SerialBT.print("A:  ");
   SerialBT.println(abs(countA));

    SerialBT.print("B:  ");
   SerialBT.println(abs(countB));


    SerialBT.print("(A+B)/2:  ");
    SerialBT.println((abs(countA)+abs(countB))/2);
  motoresStop();
  delay(30);
  resetEncoder();
}
//================= RUN SCRIPT =================
static inline void Running() {
  static uint8_t step = 0;

  switch (step) {

    case 0:   // rẽ trái
      go(31);
      step++;
      break;

    case 1:   // đi thẳng PID
      turnLeft;
      step++;
      break;

    case 2:   // rẽ phải
      go(31);
      step++;
      break;

    case 3:   // đi thẳng PID
      turnLeft;
      step++;
      break;

    case 4:   // rẽ phải
      go(31);
      step++;
      break;

    case 5:   // đi thẳng PID
      turnLeft;
      step++;
      break;

    case 6:   // rẽ phải
      go(31);
      step++;
      break;

    default:  // kết thúc
      motoresStop();
      break;
  }
}
#endif