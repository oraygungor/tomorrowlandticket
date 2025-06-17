import os
import json
import traceback
import time
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import requests

# --- Configuration ---
URL = "https://www.viagogo.com/Festival-Tickets/International-Festivals/Tomorrowland-Festival-Tickets/E-156659906?quantity=2"
PRICE_THRESHOLD = 210.0

# --- Environment-Specific Setup ---
IS_ON_RENDER = os.environ.get("RUNNING_ON_RENDER", "false").lower() == "true"

# --- IMPORTANT: FOR LOCAL MAC TESTING ONLY ---
# Paste the path to the chromedriver file you downloaded.
# This will be IGNORED when running on Render.
YOUR_MAC_DRIVER_PATH = "/Users/yourname/path/to/your/chromedriver" 

# JSONBin.io Configuration
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")
JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
JSONBIN_URL_LATEST = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"

# Gmail Configuration
SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = os.environ.get("GMAIL_RECIPIENT_EMAIL")


def get_current_price(url):
    """
    Launches a stealth browser to get the price.
    It uses a different setup for Render vs. a local Mac.
    """
    print("--- Starting Price Extraction ---")
    
    options = uc.ChromeOptions()
    driver = None
    
    try:
        if IS_ON_RENDER:
            # --- RENDER SETUP ---
            print("Running on Render. Using automatic driver detection.")
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            driver = uc.Chrome(options=options)
        else:
            # --- LOCAL MAC SETUP ---
            print(f"Running locally. Using manual driver path: {YOUR_MAC_DRIVER_PATH}")
            if "yourname/path" in YOUR_MAC_DRIVER_PATH:
                 raise Exception("Please update the 'YOUR_MAC_DRIVER_PATH' variable in the script before running locally.")
            driver = uc.Chrome(driver_executable_path=YOUR_MAC_DRIVER_PATH, options=options)

        print(f"Navigating to URL: {url}")
        driver.get(url)

        try:
            print("Looking for cookie consent pop-up...")
            cookie_button_xpath = "//button[contains(text(), 'Allow All')]"
            cookie_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, cookie_button_xpath))
            )
            print("Found and clicked the 'Allow All' button.")
            cookie_button.click()
            time.sleep(2)
        except TimeoutException:
            print("Cookie banner not found or already handled. Continuing.")

        print("Waiting for main ticket data to load...")
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.ID, "index-data"))
        )
        print("Ticket data loaded successfully!")

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        script_tag = soup.find('script', {'id': 'index-data'})
        
        if not script_tag:
            raise Exception("Could not find 'index-data' script tag.")

        json_data = json.loads(script_tag.string)
        listings = json_data.get('grid', {}).get('items', [])
        
        min_price = float('inf')
        for item in listings:
            if 'rawPrice' in item and item.get('availableTickets', 0) > 0:
                price = float(item['rawPrice'])
                if price < min_price:
                    min_price = price
        
        if min_price == float('inf'):
            print("Could not find any available tickets to determine a price.")
            return None
        
        print(f"Lowest price found: €{min_price:.2f}")
        return min_price

    except Exception as e:
        print("\n--- An Error Occurred During Price Extraction ---")
        print(traceback.format_exc())
        if driver:
            driver.save_screenshot('error_screenshot.png')
            print("Saved a screenshot to 'error_screenshot.png' for debugging.")
        return None
    finally:
        if driver:
            driver.quit()
            print("Browser closed.")
            
def get_last_price_from_jsonbin():
    if not all([JSONBIN_API_KEY, JSONBIN_BIN_ID]): return None
    print("Attempting to retrieve last known price from JSONBin.io...")
    headers = {'X-Master-Key': JSONBIN_API_KEY}
    try:
        response = requests.get(JSONBIN_URL_LATEST, headers=headers, timeout=10)
        response.raise_for_status()
        last_data = response.json().get('record', {})
        last_price = last_data.get('lowest_price_eur')
        if last_price:
            print(f"Successfully retrieved last price: €{last_price:.2f}")
            return float(last_price)
        else:
            print("No previous price found in bin.")
    except Exception as e:
        print(f"Could not retrieve last price: {e}")
    return None

def send_email_alert(price):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        print("Email credentials are not set. Skipping email alert.")
        return
    subject = f"Price Alert! Tomorrowland Ticket is now €{price:.2f}"
    body = (
        f"The price for the Tomorrowland ticket has dropped to €{price:.2f}, "
        f"which is below your threshold of €{PRICE_THRESHOLD:.2f}.\n\n"
        f"Check it out now: {URL}"
    )
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            print("SUCCESS: Email alert sent!")
    except Exception as e:
        print(f"FAILURE: Failed to send email: {e}")

def update_jsonbin(price):
    if not all([JSONBIN_API_KEY, JSONBIN_BIN_ID]):
        print("JSONBin credentials not set. Skipping update.")
        return
    print("Updating price log on JSONBin.io...")
    headers = { 'Content-Type': 'application/json', 'X-Master-Key': JSONBIN_API_KEY }
    data = { "last_checked_utc": datetime.utcnow().isoformat(), "lowest_price_eur": float(f"{price:.2f}") }
    try:
        response = requests.put(JSONBIN_URL, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        print(f"SUCCESS: Updated JSONBin.io with new price: €{price:.2f}")
    except requests.exceptions.RequestException as e:
        print(f"FAILURE: Error updating JSONBin.io: {e}")

def main():
    """Main function to run the price checker."""
    print(f"--- Running Price Check at {datetime.now()} ---")
    
    last_price = get_last_price_from_jsonbin()
    current_price = get_current_price(URL)
    
    if current_price is None:
        print("Execution stopped: Could not retrieve the current price.")
        print("--- Price Check Finished (with errors) ---")
        return

    # Compare prices and log the change
    if last_price is not None:
        if current_price == last_price:
            print(f"Status: Price has not changed from the last check (€{current_price:.2f}).")
        else:
            change_direction = "dropped" if current_price < last_price else "increased"
            print(f"Status: Price has {change_direction}! Previous: €{last_price:.2f}, Current: €{current_price:.2f}")

    # Update JSONBin with the new price
    update_jsonbin(current_price)
    
    # Check if the price is below the threshold and send an alert
    print("Checking against price threshold...")
    if current_price <= PRICE_THRESHOLD:
        print(f"Action: Price (€{current_price:.2f}) is at or below the €{PRICE_THRESHOLD:.2f} threshold.")
        send_email_alert(current_price)
    else:
        print(f"Action: Price (€{current_price:.2f}) is higher than the €{PRICE_THRESHOLD:.2f} threshold. No email sent.")
        
    print("--- Price Check Finished ---")


if __name__ == "__main__":
    main()
