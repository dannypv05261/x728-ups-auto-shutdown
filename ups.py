#!/usr/bin/env python
import struct
import smbus
import time
import sys
import os
import subprocess
import logging
import logging.handlers
import RPi.GPIO as GPIO
import multiprocessing
import threading
import signal

POWEROFF_PRECENT_THRESHOLD = 10
POWER_LEFT_INTERVAL_SEC = 60
POWER_DETECTION_GPIO_PIN = 6
POWER_OFF_DEBUG = False

log = logging.getLogger('MyLogger')
log.setLevel(logging.DEBUG)
handler = logging.handlers.SysLogHandler(address = '/dev/log')
handler.setFormatter(logging.Formatter(fmt='ups[{}]: [%(levelname)s]: %(message)s'.format(os.getpid())))
#log.addHandler(logging.FileHandler('/opt/spam.log'))
log.addHandler(handler)

if not(os.geteuid() == 0):
    log.error("Should be run in root user")
    sys.exit(1)

lock = threading.Condition()
pid = os.getpid()
process = None

try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(POWER_DETECTION_GPIO_PIN, GPIO.IN)

    # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
    bus = smbus.SMBus(1)

    def read_capacity(bus):
        address = 0x36
        read = bus.read_word_data(address, 4)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        capacity = swapped/256
        return capacity

    def kill():
        global pid
        os.kill(pid, signal.SIGINT)

    def poweroff():
        global POWEROFF_PRECENT_THRESHOLD
        global POWER_OFF_DEBUG
        global POWER_LEFT_INTERVAL_SEC
        try:
            log.info("Succeeded to enter poweroff countdown")
            while read_capacity(bus) >= POWEROFF_PRECENT_THRESHOLD:
                log.warn("Battery is running out. Battery left %5i%%" % read_capacity(bus))
                time.sleep(POWER_LEFT_INTERVAL_SEC)
            log.error('Power capacity < {}. Poweroff!!!!'.format(POWEROFF_PRECENT_THRESHOLD))
            if not(POWER_OFF_DEBUG):
                os.system('poweroff')
            kill()
        except Exception as e:
            logging.error('Error at %s', 'division', exc_info=e)

    def my_callback(channel):
        global process
        global POWER_DETECTION_GPIO_PIN
        global lock
        try:
            # if port 6 == 1
            if GPIO.input(POWER_DETECTION_GPIO_PIN):
                log.warn("AC Power & Power Adapter failure")
                if process is None:
                    lock.acquire(timeout=60)
                    process = multiprocessing.Process(target=poweroff)
                    process.start()
                    lock.release()
                else:
                    log.info("Poweroff countdown has already been started. Skipped")
            # if port 6 != 1
            else:
                log.info("AC Power & Power Adapter OK now")
                if process is not None:
                    lock.acquire(timeout=60)
                    try:
                        for i in range(0, 5):
                            if process.is_alive():
                                break
                            log.warn("Failed to terminate poweroff countdown")
                            time.sleep(5)
                        process.terminate()
                        process = None
                        log.info("Poweroff countdown terminated")
                    except Exception as e:
                        logging.error('Error at %s', 'division', exc_info=e)
                    finally:
                        lock.release()
        except Exception as e:
            logging.error('Error at %s', 'division', exc_info=e)
            kill()

    GPIO.add_event_detect(POWER_DETECTION_GPIO_PIN, GPIO.BOTH, callback=my_callback)

    log.info("Power failture detection started")
    # first check, since there is no event trigger
    if read_capacity(bus) < POWEROFF_PRECENT_THRESHOLD:
        my_callback(POWER_DETECTION_GPIO_PIN)
    threading.Event().wait()
except Exception as e:
    logging.error('Error at %s', 'division', exc_info=e)
    kill()
