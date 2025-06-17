import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from datetime import datetime

# --- Configuration ---
# These will be loaded from environment variables for security.
URL = "https://www.viagogo.com/Festival-Tickets/International-Festivals/Tomorrowland-Festival-Tickets/E-156659906?quantity=2"
PRICE_THRESHOLD = 210.0

# JSONBin.io Configuration
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")
JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"

# Gmail Configuration for sending email alerts
SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD") # IMPORTANT: Use a Google App Password
RECIPIENT_EMAIL = os.environ.get("GMAIL_RECIPIENT_EMAIL")

def get_lowest_price(url):
    """Fetches the webpage, parses it, and extracts the lowest ticket price."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the script tag containing the ticket data
        script_tag = soup.find('script', {'id': 'index-data'})
        if not script_tag:
            print("Error: Could not find the 'index-data' script tag.")
            return None

        # Extract and parse the JSON data
        json_data = json.loads(script_tag.string)
        
        listings = json_data.get('grid', {}).get('items', [])
        if not listings:
            print("Error: No ticket listings found in the JSON data.")
            return None
            
        # Find the minimum price from all available listings
        min_price = float('inf')
        for item in listings:
            if 'rawPrice' in item and item.get('availableTickets', 0) > 0:
                price = float(item['rawPrice'])
                if price < min_price:
                    min_price = price
        
        if min_price == float('inf'):
            print("Could not determine the minimum price from available tickets.")
            return None
            
        return min_price

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        print(f"Error parsing page data: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return None

def send_email_alert(price):
    """Sends an email notification via Gmail if the price is below the threshold."""
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        print("Email credentials are not set. Skipping email alert.")
        return

    subject = f"Price Alert! Tomorrowland Ticket is now €{price:.2f}"
    body = (
        f"The price for the Tomorrowland ticket has dropped to €{price:.2f}, "
        f"which is below your threshold of €{PRICE_THRESHOLD:.2f}.\n\n"
        f"Buy it now: {URL}"
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
            print("Email alert sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

def update_jsonbin(price):
    """Updates a JSONBin.io bin with the latest price data."""
    if not all([JSONBIN_API_KEY, JSONBIN_BIN_ID]):
        print("JSONBin API Key or Bin ID is not set. Skipping update.")
        return

    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': JSONBIN_API_KEY
    }
    
    data = {
        "last_checked_utc": datetime.utcnow().isoformat(),
        "lowest_price_eur": price
    }
    
    try:
        response = requests.put(JSONBIN_URL, headers=headers, json=data)
        response.raise_for_status()
        print(f"Successfully updated JSONBin.io with price: €{price:.2f}")
    except requests.exceptions.RequestException as e:
        print(f"Error updating JSONBin.io: {e}")

def main():
    """Main function to run the price checker."""
    print(f"--- Running Price Check at {datetime.now()} ---")
    lowest_price = get_lowest_price(URL)
    
    if lowest_price is not None:
        print(f"Current lowest price found: €{lowest_price:.2f}")
        
        # Update JSONBin.io with the found price
        update_jsonbin(lowest_price)
        
        # Check if the price is below the threshold and send an email
        if lowest_price <= PRICE_THRESHOLD:
            print(f"Price is below the threshold of €{PRICE_THRESHOLD:.2f}!")
            send_email_alert(lowest_price)
        else:
            print(f"Price is not below the threshold.")
    else:
        print("Could not retrieve the lowest price. Check logs for errors.")

if __name__ == "__main__":
    main()
