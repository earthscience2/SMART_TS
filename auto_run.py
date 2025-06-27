import auto_inp
import auto_sensor
import auto_inp_to_frd
import auto_frd_to_vtk
import time

if __name__ == '__main__':
    while True:
        auto_sensor.auto_sensor_data()
        time.sleep(10)
        auto_inp.auto_inp()
        time.sleep(10)
        auto_inp_to_frd.convert_all_inp_to_frd()
        time.sleep(10)
        auto_frd_to_vtk.convert_all_frd_to_vtk()
        time.sleep(1200)

