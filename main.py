import mpu6050
from machine import *
import network
import esp32
import time
import binascii
import urequests
import json

motion_detected = False
active = False

green_led = Pin(26, Pin.OUT)
red_led = Pin(25, Pin.OUT)

sample_timer = Timer(1)
motion_detect_timer = Timer(2)


ssid = ""
password = ""
wlan = network.WLAN(network.STA_IF)

i2c = I2C(scl=Pin(22), sda=Pin(23))
mpu = mpu6050.accel(i2c)

thingspeak_url = 'https://api.thingspeak.com/channels/1724153/fields/1.json?api_key=&results=1'
ifttt_url = 'https://maker.ifttt.com/trigger/Motion_Detected/with/key/'
test_ifttt_url = ifttt_url + '?value1=1&value2=2&value3=3'

# hardcoded offsets found from calibration
ac_offsets = {
    "AcX" : 990,
    "AcY" : -199,
    "AcZ" : -1184,
    "Tmp" : 0,
    "GyX" : 0,
    "GyY" : 0,
    "GyZ" : 0
}

def main():
    global active
    global motion_detected
    green_led.off()
    red_led.off()

    calibrate()
    get_connection()
    sample_timer.init(mode=Timer.PERIODIC, period=30000, callback=sample_timer_callback)
    motion_detect_timer.init(mode=Timer.ONE_SHOT, period=10000, callback=motion_detect_timer_callback)
    
    while True:
        # activate will trigger on timeout and set this var in callback
        if (active):
            green_led.on()

            # Sample the mpu
            ac_vals = mpu.get_values()
            ac_adjusted = {key: ac_vals[key] - ac_offsets.get(key, 0) for key in ac_vals}
            if (ac_adjusted.get('AcX') > 500 or ac_adjusted.get('AcY') > 500 or ac_adjusted.get('AcZ') > 500):
                # if the first occurence of motion detected, send a notification with the values we just got
                if not motion_detected:
                    motion_detected = True
                    send_notification(ac_adjusted)
                    motion_detect_timer.init(mode=Timer.ONE_SHOT, period=10000, callback=motion_detect_timer_callback)
                red_led.on()
            else:
                red_led.off()
        else:
            green_led.off()
            red_led.off()

        time.sleep(0.1)

def calibrate():
    num_iterations = 200
    ac_sum = {
        "AcX_sum" : 0,
        "AcY_sum" : 0,
        "AcZ_sum" : 0
    }
    ac_avg = {}

    printProgressBar(0, num_iterations, prefix = 'Calibrating:', suffix = 'Complete', length = 50)
    for i in range(num_iterations):
        vals = mpu.get_values()
        ac_sum["AcX_sum"] = ac_sum["AcX_sum"] + vals["AcX"]
        ac_sum["AcY_sum"] = ac_sum["AcY_sum"] + vals["AcY"]
        ac_sum["AcZ_sum"] = ac_sum["AcZ_sum"] + vals["AcZ"]
        time.sleep(0.1)
        printProgressBar(i+1, num_iterations, prefix = 'Calibrating:', suffix = 'Complete', length = 50)

    ac_avg["AcX_avg"] = round(ac_sum["AcX_sum"] / num_iterations)
    ac_avg["AcY_avg"] = round(ac_sum["AcY_sum"] / num_iterations)
    ac_avg["AcZ_avg"] = round(ac_sum["AcZ_sum"] / num_iterations)
    
    ac_offsets["AcX"] = ac_avg["AcX_avg"]
    ac_offsets["AcY"] = ac_avg["AcY_avg"]
    ac_offsets["AcZ"] = ac_avg["AcZ_avg"]
    
    print(ac_offsets)

def get_connection():
    if wlan.isconnected():
        return wlan
    
    connected = False
    try:
        time.sleep(1)
        if wlan.isconnected():
            return wlan
        
        wlan.active(True)
        networks = wlan.scan()
        print('Available networks:', str([i[0].decode('utf-8') for i in networks]))
        
        connected = do_connect(ssid, password)

    except OSError as e:
        print("exception", str(e))
        
    return wlan if connected else None

def do_connect(ssid, password):
    wlan.active(True)
    if not wlan.isconnected():
        wlan.status()
        print('connecting to network', ssid)
        wlan.connect(ssid, password)
        for retry in range(100):
            connected = wlan.isconnected()
            if connected:
                break
            time.sleep(0.1)
            print('.', end='')
        if connected:
            print('\nconnected to:', ssid)
            print('IP Address:', wlan.ifconfig()[0])
        else:
            print('\nnot connected to: ' + ssid)
    return connected

def sample_timer_callback(t):
    '''Sample thingspeak for activation status'''
    global active
    url = thingspeak_url
    res = http_req(url, 'GET')

    # catch bad responses
    try:
        res_dict = json.loads(res)
        field1 = res_dict.get('feeds')[0].get('field1').strip()
        if field1 is not None:
            if (field1 == 'activate'):
                active = True
            else:
                active = False
        print(field1)
    except ValueError as e:
        print("exception", str(e))
        
def motion_detect_timer_callback(t):
    global motion_detected
    motion_detected = False
    
def send_notification(ac_vals):
    acx = round(ac_vals.get('AcX') / 16384, 2)
    acy = round(ac_vals.get('AcY') / 16384, 2)
    acz = round(ac_vals.get('AcZ') / 16384, 2)
    url = f'{ifttt_url}?value1={acx}&value2={acy}&value3={acz}'
    http_req(url, 'POST')
    print('Sent Notification')

def http_req(req_url, req_type):
    res = None
    if req_type == 'POST':
        res = urequests.post(url=req_url).text
    elif req_type == 'GET':
        res = urequests.get(url=req_url).text

    return res

# Print iterations progress
def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end = printEnd)
    # Print New Line on Complete
    if iteration == total:
        print()

if __name__ == "__main__":
    main()