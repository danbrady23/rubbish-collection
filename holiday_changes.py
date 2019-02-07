import requests
import re
import pickle
import dateutil.parser as dparser
from bs4 import BeautifulSoup as bs

url = 'https://www.lewisham.gov.uk/myservices/wasterecycle/Pages/Bank-holiday-collections.aspx'

def extract_dates(column):
	days = table.find_all("td", class_= re.compile(column))
	dates = [dparser.parse(option.text, fuzzy = True) for option in days]

	return dates

response = requests.get(url)

soup = bs(response.content, 'html.parser')

tables = soup.find_all(class_="lbl-styleTable-default")

holiday_changes = {}

for table in tables:
	regular = extract_dates("Even")
	altered = extract_dates("Odd")

	holiday_changes.update(dict(zip(regular, altered)))

with open('holiday_changes.pkl', 'w') as file:
	pickle.dump(holiday_changes, file)