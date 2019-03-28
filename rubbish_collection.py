import os
import pickle
import re
import sys
from datetime import date, timedelta

import dateutil.parser as dparser
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait as WDwait

try:  # This checks for RPi library. If it exists then the script is probably being run on a RPi
    import RPi.GPIO as GPIO
    useGPIO = True
except ImportError:  # If it doesn't then we cant update LEDs anyway so disable that part of the script
    print('Module not found. Not updating LEDs')
    useGPIO = False


# Set user defined variables
urls = {
    "input": 'https://www.lewisham.gov.uk/myservices/wasterecycle/your-bins/collection',
    "result": "https://lewisham.gov.uk/myservices/wasterecycle/your-bins/collection/find-your-collection-day-result"
}

address = {
        "House_no": "20",
        "Postcode": "SE128LX"
}

leds = {
    "food": 11,
    "recycling": 13,
    "refuse": 15
}


# Main function
def main():
    os.chdir(os.path.dirname(sys.argv[0]))  # Change directory to script location

    file_name = 'collection_dates.pkl'

    # Either load or retrieve collection dates
    collection_dates = load_or_update(file_name, update_collection_dates,
                                      url=urls, address_details=address, rubbish=leds.keys())

    # If the RPi.GPIO module was successfully imported then update the leds
    if useGPIO:
        update_leds(collection_dates, leds)


# Load or update dates
def load_or_update(file_name, update_function, **kwargs):

    if os.path.isfile(file_name):  # If the file exists load it
        with open(file_name, 'rb') as file:
            dates = pickle.load(file)

        if date.today() >= dates["next_update"]:  # Check the next update date, it it has passed then update
            dates = update_function(file_name, **kwargs)
    else:  # Otherwise just update
        dates = update_function(file_name, **kwargs)

    return dates


# Update and save collection dates
def update_collection_dates(file_name, url, address_details, rubbish):
    rounds_text = get_collection_info(url['result'], address_details)  # Get raw text from site
    collection_dates = parse_collection_text(rounds_text, rubbish)  # Parse text for collection dtaes
    collection_dates = holiday_adjustments(url['input'], collection_dates)  # Adjust dates based on holidays

    collection_dates['next_update'] = dparser.parse("Sunday", fuzzy=True, dayfirst=True)  # Add date for next update

    # Save dates into file
    with open(file_name, 'wb') as file:
        pickle.dump(collection_dates, file)

    return collection_dates


# Get collection info using selenium
def get_collection_info(url, address_details):
    browser = open_browser(url)  # Need to start in results page to get this to work, no idea why...

    # Find input page link on results page and click it
    link_to_input = browser.find_element_by_partial_link_text("collection day")
    link_to_input.click()

    # Find search bar and submit button
    search_bar = browser.find_element_by_class_name('js-address-finder-input')
    search_button = browser.find_element_by_class_name('js-address-finder-step-address')

    # Put the postcode in the searchbar and then
    search_bar.send_keys(address_details["Postcode"])
    browser.execute_script("arguments[0].click();", search_button)

    # Wiat for the address selector box to appear
    select_box = WDwait(browser, 5).\
        until(ec.visibility_of_element_located((By.CLASS_NAME, 'js-address-finder-select')))

    # Get all the options from the box
    addresses = Select(select_box)

    # Find the specific address using the house number
    found_address = [opt.text for opt in addresses.options if address_details["House_no"] in opt.text]

    # Might need error control here: What if address is not found?

    # Select that address
    addresses.select_by_visible_text(found_address[0])

    # Get the section that contains the result
    result = WDwait(browser, 5).until(ec.visibility_of_element_located((By.CLASS_NAME, "js-find-collection-result")))

    # Extract the text from that section
    collection_text = result.text

    browser.close()

    return collection_text

    # This may still be useful
    # try:
    #     result = WDwait(browser, 5).\
    #         until(ec.visibility_of_element_located((By.CLASS_NAME, "js-find-collection-result")))
    #
    #     return result.text
    # finally:
    #     browser.close()


# Open browser and go to url
def open_browser(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")

    if useGPIO:  # If we're on a RPi then the chromedriver location is different
        browser = webdriver.Chrome('/usr/lib/chromium-browser/chromedriver', options=chrome_options)
    else:
        browser = webdriver.Chrome(options=chrome_options)

    browser.get(url)

    return browser


# Parse the results text for dates
def parse_collection_text(rounds_text, search_strings):

    # Generate regex pattern for splitting up the raw result text
    reg_pattern = "(%s)" % "|".join(search_strings)

    rounds_text = rounds_text.lower()
    rounds_list = re.split(reg_pattern, rounds_text)  # Split the raw text into a list

    collection_dates = {}

    for search_str in search_strings:  # For each of the rubbish types
        # Find the index in the list that contians that type
        index = [i for i, s in enumerate(rounds_list) if search_str in s]

        # Parse the following item for a date
        collection_datetime = dparser.parse(rounds_list[index[0]+1], fuzzy=True, dayfirst=True)
        collection_dates[search_str] = collection_datetime.date()

    return collection_dates


# Adjust collection dates for holidays
def holiday_adjustments(url, collection_dates):

    file_name = 'holiday_changes.pkl'

    holiday_dates = load_or_update(file_name, update_holiday_dates, url=url)

    # See if any of the collection dates match a date in the holiday dict
    for k, v in collection_dates.items():
        if v in holiday_dates.keys():  # If it does then assign the revised date to it
            collection_dates[k] = holiday_dates[v]

    return collection_dates


# Gets updated holiday dates
def update_holiday_dates(file_name, url):

    # Set when the data should be refreshed
    holiday_dates = {"next_update": date.today()+timedelta(days=7)}

    browser = open_browser(url)

    try:  # Try and open holiday changes webpage
        holiday_link = browser.find_element_by_partial_link_text("collection day will change")
        browser.execute_script("arguments[0].click();", holiday_link)

        # Get table from page
        table = browser.find_element_by_class_name("markup-table")
        rows = table.find_elements_by_tag_name("tr")

        for row in rows:  # Run through each row of the table
            cols = row.find_elements_by_tag_name("td")
            try:  # Try and parse dates from each of the columns in that row
                original_date = dparser.parse(cols[0].text, fuzzy=True, dayfirst=True).date()
                new_date = dparser.parse(cols[1].text, fuzzy=True, dayfirst=True).date()
                holiday_dates[original_date] = new_date
            except:  # Some columns may not contain dates and this exception skips them to prevent confusion
                continue

    finally:  # but do this anyway if opening the page doesn't work
        with open(file_name, 'wb') as file:
            pickle.dump(holiday_dates, file)

        browser.close()
        return holiday_dates


# Display collection info through lights
def update_leds(collection_dates, leds):

    # Work out tomorrows date
    date_tomorrow = date.today() + timedelta(days=1)

    # Set-up GPIO on RPi
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    GPIO.setup(list(leds.values()), GPIO.OUT, initial=GPIO.LOW)

    # Run through each element in collection dates
    for col_item, col_date in collection_dates.items():
        if col_item == "next_update":  # Skip the next_update item
            continue
        elif col_date == date_tomorrow:
            GPIO.output(leds[col_item], 1)
        else:
            GPIO.output(leds[col_item], 0)


if __name__== "__main__":
    main()
