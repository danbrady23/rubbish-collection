import pickle
import os, sys
import RPi.GPIO as GPIO
from datetime import datetime, timedelta

os.chdir(os.path.dirname(sys.argv[0]))

with open('collection_dates.pkl', 'r') as file:
	collection_dates = pickle.load(file)

date_tomorrow = datetime.now().date() + timedelta(days=1)

leds = {"food": 11,
		"recycling": 13,
		"refuse": 15}

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
GPIO.setup(leds.values(), GPIO.OUT, initial = GPIO.LOW)

for item in collection_dates:
	if collection_dates[item].date() == date_tomorrow:
		GPIO.output(leds[item], 1)
	else:
		GPIO.output(leds[item], 0)
