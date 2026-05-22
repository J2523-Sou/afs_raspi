import time
import socket
try:
    import lgpio
except Exception:
    lgpio = None
try:
    import serial
except Exception:
    serial = None

# GPIO
led1 = 17
h = None
if lgpio is not None:
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, led1)
    except Exception as e:
        print("Warning: cannot open gpiochip:", e)
        h = None

HOST = "0.0.0.0"
PORT = 5001
data = []

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((HOST, PORT))
s.listen(1)
ser = None
if serial is not None:
    try:
        ser = serial.Serial("/dev/ttyAMA0", 9600, timeout=0.1)
    except Exception as e:
        print("Warning: cannot open serial /dev/ttyAMA0:", e)
        ser = None

print("Waiting for connection...")
conn, addr = s.accept()
print("Connected from", addr)
if h is not None:
    try:
        lgpio.gpio_write(h, led1, 1)
    except Exception:
        pass



while True:
    
    #Header
    head = conn.recv(1)
    if not head:
        break
    if head[0] != 0xAA:
        continue
    
    # Get 7Byte data
    receive = conn.recv(7)
    if len(receive) != 7:
        continue
    data = list(receive)
    
#    print("Data1:", data[0], " Data2:", data[1], " Data3:", data[2], " Data4:", data[3], " Data5:", data[4], " Data6:", data[5], " Data7:", data[6])
    # forward to serial if available
    if ser is not None:
        try:
            ser.write(b"\xAA")     # header
            ser.write(data)
        except Exception as e:
            print("Warning: serial write failed:", e)
            ser = None
    else:
        # serial unavailable
        pass
    
    
    time.sleep(0.0001)
    
conn.close()
s.close()