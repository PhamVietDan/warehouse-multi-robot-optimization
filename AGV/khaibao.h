#ifndef khaibao
#define khaibao
#include "BluetoothSerial.h"
BluetoothSerial SerialBT;

#define PWMA 13
#define AIN1 12
#define AIN2 14
#define STBY 27
#define BIN1 26
#define BIN2 25
#define PWMB 33
/**************** ENCODER ****************/
// LEFT encoder
#define ENCA_A 16
#define ENCA_B 17

// RIGHT encoder (tránh 21/22)
#define ENCB_A 22
#define ENCB_B 21

#define S1 32
#define S2 35
#define S3 34
#define S4 39
#define S5 36
//========================RFID
#include <SPI.h>
#include <MFRC522.h>
#define SS_PIN   5    // SDA / CS
#define RST_PIN  4    // RST
MFRC522 rfid(SS_PIN, RST_PIN);
static unsigned long lastRF = 0;
// ================= LINE STATE =================
#define BAMLINE 0
#define LEFT   1
#define RIGHT  2
#define BLACK  3
#define MATLINE   4
// ------------------- KHAI BÁO BIẾN CẢM BIẾN -------------------
const uint8_t num=5;
uint16_t sensorValue[num];     // giá trị analog đọc được
uint16_t S[num];    // giá trị 0/1 sau khi so sánh
uint16_t ValueMax[num];
uint16_t ValueMin[num];
uint16_t threshold[num]; 
const uint8_t sensorPin[num] = {S1,S2,S3,S4,S5};
int weightValue[num] = {-10,-8,0,8,10 }; // trọng số giãn cách
int sumSensor;
int sumWeight;
uint8_t mode = 0;
bool calibrated = false;
float error, previous_error;
float currPos;
float cenPos = 0;   // trung tâm
float ePrev = 0;
float eCurr;  
float u;
float dE;
float eSum = 0;
float Ki =0 ;
float Kp = 12;
float Kd = 25;
float integral = 0;
int baseSpeed = 200;   // tốc độ cơ bản
int speedmax=255;
int lastTurn = 0;  // -1 = trái, 0 = thẳng, 1 = phải
// ================= TIMER =================
unsigned long lostTime = 0;
unsigned long turnTime = 0;
uint8_t prevState = BAMLINE;
unsigned long startTime = 0;
bool startDone = false;
#define LINETIME      200    // ms
#define EEPROM_MAGIC 0xA5
bool done = false;

#define STEP_PULSE 31*(4000/22)/6
char heading = 'N';   // N E S W


long lastSendPulse = 0;


#endif