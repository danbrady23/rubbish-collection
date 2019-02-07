import requests
import re, os, sys
import pickle
import dateutil.parser as dparser
from bs4 import BeautifulSoup, SoupStrainer
from post_body import shared_body, extra_body1, extra_body2

os.chdir(os.path.dirname(sys.argv[0]))

address_details = {
	"House_no":"20",
	"Postcode": "SE128LX"
}

url = 'https://www.lewisham.gov.uk/myservices/wasterecycle/your-bins/collection/Pages/default.aspx'
rubbish = ["food", "recycling", "refuse"]

# Gets the initial aspx variables
def get_init_aspx_vars():

	response = requests.get(url)
	init_soup = BeautifulSoup(response.content, 'html.parser')

	update_aspx_vars(init_soup)

# Updated aspx variables and writes them to the shared body
def update_aspx_vars(soup):

	viewstate = soup.select('#__VIEWSTATE')[0]['value']
	requestdigest = soup.select('#__REQUESTDIGEST')[0]['value']
	eventvalidation = soup.select('#__EVENTVALIDATION')[0]['value']
	viewstategenerator = soup.select('#__VIEWSTATEGENERATOR')[0]['value']

	formData = {
		"__VIEWSTATE": viewstate,
		"__REQUESTDIGEST": requestdigest,
		"__EVENTVALIDATION": eventvalidation,
		"__VIEWSTATEGENERATOR": viewstategenerator
	}

	shared_body.update(formData)

# Generates the post payload, posts it to the url, and returns soup of the response
def gen_and_post_payload(added_body):

	payload = shared_body.copy()
	payload.update(added_body)

	response = requests.post(url, data = payload)

	soup = BeautifulSoup(response.content, 'html.parser')

	return soup

# Finds address ID based on House number and Postcode
def find_address_id(address):

	extra_body1.update({'ctl00$PlaceHolderPages$RoundsInformation$ctl00$ctl02': address['Postcode']})
	address_soup = gen_and_post_payload(extra_body1)

	update_aspx_vars(address_soup)

	address_id = [option['value'] for option in address_soup.find_all('option') if address['House_no'] in option.text]
	address_id = int(address_id[0])

	return address_id

# Gets collection strings based on address ID
def get_collection_dates(address_id):

	extra_body2.update({'ctl00$PlaceHolderPages$RoundsInformation$ctl00$ctl04': address_id})
	rounds_soup = gen_and_post_payload(extra_body2)
	
	rounds_soup = rounds_soup.find(class_ ='roundsFinder')

	# turn the html into a list of stings
	rounds_text = rounds_soup.get_text() # Get raw text
	rounds_text = rounds_text.replace(u'\xa0', u' ') # Remove non-breaking spaces
	rounds_text = rounds_text.replace('\r','').replace('\n','') # Remove line breaks
	rounds_list = re.split('[:.]',rounds_text) # Splits text into list using : and .
	rounds_list = [x.lstrip() for x in rounds_list] # Strip leading whitespace
	return rounds_list

# Parses collection strings for dates
def find_collection_date(search_str):
	index = [i for i, s in enumerate(rounds_list) if search_str.lower() in s.lower()]
	if search_str.lower() == "refuse":
		next_collection = dparser.parse(rounds_list[index[0]+1],fuzzy = True, dayfirst = True)
	else:
		next_collection = dparser.parse(rounds_list[index[0]],fuzzy = True, dayfirst = True)

	with open('holiday_changes.pkl', 'r') as file:
		holiday_dates = pickle.load(file)

	if next_collection in holiday_dates.keys():
		next_collection = holiday_dates[next_collection]

	return next_collection


# Main body of script
get_init_aspx_vars()
address_id = find_address_id(address_details)
rounds_list = get_collection_dates(address_id)
collection_dates = map(find_collection_date, rubbish)
collection_dates = dict(zip(rubbish, collection_dates))

# Write data to file
with open('collection_dates.pkl', 'w') as file:
	pickle.dump(collection_dates, file)


# Todo:
#   - Error handling