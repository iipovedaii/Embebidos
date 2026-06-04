# Inicializacion unificada de perifericos reales.

import time

_initialized = False


def setup(cfg):
    """Llama una sola vez desde main si HARDWARE_ENABLED."""
    global _initialized
    if _initialized:
        return
    import hardware_pins as pins
    import battery
    import hcsr04
    import motors_l298n
    import oled_display
    import i2c_bus
    import mearm_controller

    battery._get_adc(pins.BATTERY_ADC_PIN)
    hcsr04.init(pins.USONIC_TRIG_PIN, pins.USONIC_ECHO_PIN)
    motors_l298n.init(
        pins.MOTOR_L_IN1,
        pins.MOTOR_L_IN2,
        getattr(pins, "MOTOR_L_ENA", None),
        pins.MOTOR_R_IN3,
        pins.MOTOR_R_IN4,
        getattr(pins, "MOTOR_R_ENB", None),
        getattr(cfg, "MOTOR_PWM_FREQ", 1000),
        use_pwm_enable=getattr(cfg, "MOTOR_USE_PWM_ENABLE", True),
    )
    motors_l298n.configure(cfg)
    motors_l298n.stop()

    sda = getattr(cfg, "I2C_SDA_PIN", pins.I2C_SDA_PIN)
    scl = getattr(cfg, "I2C_SCL_PIN", pins.I2C_SCL_PIN)
    freq = getattr(cfg, "I2C_FREQ", 100000)
    bus = i2c_bus.get_bus(sda, scl, freq)
    time.sleep_ms(100)

    if getattr(cfg, "OLED_ENABLED", True):
        oled_addr = getattr(cfg, "OLED_I2C_ADDR", pins.OLED_I2C_ADDR)
        oled_w = getattr(cfg, "OLED_WIDTH", pins.OLED_WIDTH)
        oled_h = getattr(cfg, "OLED_HEIGHT", pins.OLED_HEIGHT)
        try:
            oled_display.init(bus=bus, addr=oled_addr, width=oled_w, height=oled_h, cfg=cfg)
        except Exception as e:
            print("[hw] OLED omitido:", e)

    if getattr(cfg, "MEARM_ENABLED", True):
        mearm_controller.init(cfg)
    else:
        mearm_controller.deinit()

    if getattr(cfg, "CAMERA_ENABLED", False):
        import ov7670

        ov7670.init(cfg, pins)

    _initialized = True
    i2c_label = "I2C GP4/5 (OLED+OV7670)" if getattr(cfg, "CAMERA_ENABLED", False) else "I2C GP4/5 (OLED)"
    if motors_l298n.is_tank_parallel():
        mot = "L298N tanque GP14/15"
    elif pins.MOTOR_R_IN3 is not None:
        mot = "L298N FULL GP14-15 IN1/2 GP7/8 IN3/4 GP6/16 ENA/ENB"
    else:
        mot = "L298N GP14-15"
    print(
        "[hw] bateria GP26, usonic GP2/3, " + mot
        + ", " + i2c_label
        + (", MeArm GP17/18/20/21" if mearm_controller.is_hardware_enabled() else ", MeArm OFF")
        + (", OV7670 (legacy)" if getattr(cfg, "CAMERA_ENABLED", False) else ", cam=ESP32-CAM Wi-Fi")
    )
