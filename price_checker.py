import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from datetime import datetime

# --- Configuration ---
URL = "https://www.viagogo.com/Festival-Tickets/International-Festivals/Tomorrowland-Festival-Tickets/E-156659906?quantity=2"
PRICE_THRESHOLD = 210.0

# JSONBin.io Configuration
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")
JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
JSONBIN_URL_LATEST = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"


# Gmail Configuration
SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = os.environ.get("GMAIL_RECIPIENT_EMAIL")

def get_last_price_from_jsonbin():
    """Retrieves the last recorded price from your JSONBin.io bin."""
    if not all([JSONBIN_API_KEY, JSONBIN_BIN_ID]):
        print("JSONBin credentials not set. Cannot retrieve last price.")
        return None

    print("Attempting to retrieve last known price from JSONBin.io...")
    headers = {
        'X-Master-Key': JSONBIN_API_KEY
    }
    try:
        response = requests.get(JSONBIN_URL_LATEST, headers=headers, timeout=10)
        response.raise_for_status()
        # The actual data is nested under the 'record' key in the response
        last_data = response.json().get('record', {})
        last_price = last_data.get('lowest_price_eur')
        
        if last_price:
            print(f"Successfully retrieved last price: €{last_price:.2f}")
            return float(last_price)
        else:
            print("No previous price found in bin (this might be the first run).")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Could not retrieve last price from JSONBin.io (Request Error): {e}")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Could not parse last price from JSONBin.io response: {e}")
    return None

def get_current_price(url):
    """Fetches and extracts the current lowest ticket price from the URL."""
    print("Getting current data from viagogo...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        script_tag = soup.find('script', {'id': 'index-data'})
        if not script_tag:
            print("Error: Could not find the 'index-data' script tag.")
            return None

        json_data = json.loads(script_tag.string)
        listings = json_data.get('grid', {}).get('items', [])
        if not listings:
            print("Error: No ticket listings found in the JSON data.")
            return None
            
        min_price = float('inf')
        for item in listings:
            # Ensure the listing has tickets and is not just a sold placeholder
            if 'rawPrice' in item and item.get('availableTickets', 0) > 0:
                price = float(item['rawPrice'])
                if price < min_price:
                    min_price = price
        
        if min_price == float('inf'):
            print("Could not determine the minimum price from available tickets.")
            return None
            
        print(f"Data retrieved successfully. Current lowest price is €{min_price:.2f}")
        return min_price

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        print(f"Error parsing page data: {e}")
    return None

def send_email_alert(price):
    """Sends an email notification via Gmail."""
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
    """Updates the JSONBin.io bin with the latest price data."""
    if not all([JSONBIN_API_KEY, JSONBIN_BIN_ID]):
        print("JSONBin credentials not set. Skipping update.")
        return

    print("Updating price log on JSONBin.io...")
    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': JSONBIN_API_KEY
    }
    
    data = {
        "last_checked_utc": datetime.utcnow().isoformat(),
        "lowest_price_eur": float(f"{price:.2f}")
    }
    
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
