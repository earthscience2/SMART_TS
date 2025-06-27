import auto_inp
import auto_sensor
import time

if __name__ == '__main__':
    while True:
        auto_sensor.auto_sensor_data()
        time.sleep(60)
        auto_inp.auto_inp()
        time.sleep(1200)
