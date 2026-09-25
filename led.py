import serial
import time

ser = serial.Serial(
    '/dev/ttyACM0',
    115200,
    timeout=1
)

def send_serial(name):
    ser.write(name.encode())
    print(f"Sent: {name}")
    ser.flush()
    time.sleep(0.1)
    print(f"シリアルをおくりました: {name}")


ser.close()
