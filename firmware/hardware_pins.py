# Mapa de pines definitivo · PCB SISEMB · Raspberry Pi Pico 2W
#
# - OV7670: NO conectada (cámara = ESP32-CAM por Wi-Fi al broker)
# - L298N: 4 IN independientes + ENA/ENB PWM
# - MeArm: 4 servos PWM directos
# - OLED I2C, HC-SR04, batería ADC
#
# Documentación PCB: docs/PINOUT_PCB.md

# ----- Batería (divisor → ADC0, max 3.3 V en el pin) -----
BATTERY_ADC_PIN = 26

# ----- HC-SR04 -----
USONIC_TRIG_PIN = 2
USONIC_ECHO_PIN = 3

# ----- I2C (OLED SSD1306 0x3C) -----
I2C_SDA_PIN = 4
I2C_SCL_PIN = 5
OLED_I2C_ADDR = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 64

# ----- L298N · diferencial (IN1-IN4 + ENA/ENB) -----
MOTOR_L_IN1 = 14
MOTOR_L_IN2 = 15
MOTOR_R_IN3 = 7
MOTOR_R_IN4 = 8
MOTOR_L_ENA = 6
MOTOR_R_ENB = 16

# ----- MeArm · PWM 50 Hz (alimentación 5-6 V externa, GND común) -----
MEARM_SERVO_BASE = 17
MEARM_SERVO_SHOULDER = 18
MEARM_SERVO_ELBOW = 20
MEARM_SERVO_GRIPPER = 21

# ----- ESP32-CAM (opcional UART; vídeo recomendado por Wi-Fi, 0 GPIO) -----
ESP32CAM_UART_TX = 10   # Pico TX → ESP32 RX
ESP32CAM_UART_RX = 9    # Pico RX ← ESP32 TX
ESP32CAM_UART_BAUD = 115200

# ----- OV7670 · retirado (no usar en PCB nueva) -----
CAM_D0 = None
CAM_D1 = None
CAM_D2 = None
CAM_D3 = None
CAM_D4 = None
CAM_D5 = None
CAM_D6 = None
CAM_D7 = None
CAM_VSYNC = None
CAM_HREF = None
CAM_PCLK = None
CAM_XCLK = None
CAM_RESET = None
CAM_PWDN = None
OV7670_I2C_ADDR = 0x21
CAM_DATA_PINS = ()

# GPIO libres para test / expansión en PCB
GPIO_NC = (0, 1, 11, 12, 13, 19, 22, 27, 28)
