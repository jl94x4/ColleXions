import random
import logging
import time
import json
import os
import sys
import requests
from plexapi.server import PlexServer
from datetime import datetime, timedelta

# Define log file path
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'collexions.log')

# Ensure the logs directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
    logging.info(f"Created log directory: {LOG_DIR}")

# Configure logging to file with UTF-8 encoding for console output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Configuration file path
CONFIG_FILE = 'config.json'

# File to store the selected collections per day
SELECTED_COLLECTIONS_FILE = 'selected_collections.json'

# Load the selected collections and clean up old entries (older than 3 days)
def load_selected_collections():
    if os.path.exists(SELECTED_COLLECTIONS_FILE):
        with open(SELECTED_COLLECTIONS_FILE, 'r', encoding='utf-8') as f:
            selected_collections = json.load(f)
    else:
        selected_collections = {}

    # Clean up entries older than 3 days
    current_date = datetime.now().date()
    week_ago_date = current_date - timedelta(days=3)

    selected_collections = {
        day: collections for day, collections in selected_collections.items()
        if datetime.strptime(day, '%Y-%m-%d').date() >= week_ago_date
    }

    return selected_collections

# Save the selected collections including entries from the past 3 days
def save_selected_collections(selected_collections):
    # Clean up old entries (older than 3 days) before saving
    current_date = datetime.now().date()
    week_ago_date = current_date - timedelta(days=3)

    selected_collections = {
        day: collections for day, collections in selected_collections.items()
        if datetime.strptime(day, '%Y-%m-%d').date() >= week_ago_date
    }

    # Save the updated collections to the file
    with open(SELECTED_COLLECTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(selected_collections, f, ensure_ascii=False, indent=4)

# Load configuration from the JSON file with UTF-8 encoding
def load_config():
    if not os.path.exists(CONFIG_FILE):
        logging.error(f"Configuration file '{CONFIG_FILE}' not found.")
        raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found.")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

# Initialize the Plex server connection
def connect_to_plex(config):
    logging.info("Connecting to Plex server...")
    plex = PlexServer(config['plex_url'], config['plex_token'])
    logging.info("Connected to Plex server successfully.")
    return plex

# Get current collections from all specified libraries
def get_collections_from_all_libraries(plex, library_names):
    all_collections = []
    for library_name in library_names:
        library = plex.library.section(library_name)
        collections = library.collections()
        all_collections.extend(collections)
    logging.info("Current collections from all libraries:")
    for collection in all_collections:
        logging.info(f"Collection: {collection.title}")
    return all_collections

# Pin the selected collections to Home and Friends' Home screens
def pin_collections(collections, config):
    for collection in collections:
        try:
            logging.info(f"Attempting to pin collection: {collection.title}")
            hub = collection.visibility()
            hub.promoteHome()
            hub.promoteShared()
            message = f"INFO - Collection '**{collection.title}**' pinned successfully to Home and Friends' Home screens."
            logging.info(message)
            # Send a message to the Discord webhook if URL is provided
            if 'discord_webhook_url' in config and config['discord_webhook_url']:
                send_discord_message(config['discord_webhook_url'], message)
        except Exception as e:
            logging.error(f"Unexpected error while pinning collection: {collection.title}. Error: {str(e)}")

# Send a message to the Discord webhook
def send_discord_message(webhook_url, message):
    data = {
        "content": message
    }
    response = requests.post(webhook_url, json=data)
    if response.status_code == 204:
        logging.info(f"Message sent to Discord: {message}")
    else:
        logging.error(f"Failed to send message to Discord. Status code: {response.status_code}, response: {response.text}")

# Unpin the currently pinned collections, honoring exclusions
def unpin_collections(plex, library_names, exclusion_list):
    logging.info("Unpinning currently pinned collections...")
    for library_name in library_names:
        for collection in plex.library.section(library_name).collections():
            if collection.title in exclusion_list:
                logging.info(f"Skipping unpinning for collection: {collection.title} (in exclusion list)")
                continue
            hub = collection.visibility()
            if hub._promoted:
                hub.demoteHome()
                hub.demoteShared()
                logging.info(f"Collection '{collection.title}' unpinned successfully.")

# Check for special scheduled collections that are within the active date range
def get_active_special_collections(config):

    current_date = datetime.now().date()  # Initialize current_date to today's date

    for special in config.get('special_collections', []):
        for collection in special['collection_names']:
            start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year).date()
            end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year).date()
            if start_date <= current_date <= end_date:
                valid_special_collections.append(collection)
                break


    import pytz  # Add timezone support
    tz = pytz.timezone("UTC")  # Set the timezone to UTC, or update this to the user's specific timezone if needed
    current_date = datetime.now(tz).date()  # Ensure current_date reflects timezone
    
    # Log start, end, and current date for each special collection evaluation
    print(f"[DEBUG] Current date for pinning: {current_date}")
    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year)
        end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year)
        print(f"[DEBUG] Evaluating Special Collection: {special['collection_names']}")
        print(f"[DEBUG] Start Date: {start_date}, End Date: {end_date}, Current Date: {current_date}")

    # Convert current_date to datetime at midnight for consistent comparison
    current_date = datetime.combine(datetime.now().date(), datetime.min.time())
    active_special_collections = []
    logging.info(f"Checking for special collections on date: {current_date}")

    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year)
        end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year)

        # Check if the current date falls within the specified date range
        if start_date <= current_date <= end_date:
            logging.info(f"Special collection '{special['collection_names']}' is active.")
            active_special_collections.extend(special['collection_names'])
        else:
            logging.info(f"Special collection '{special['collection_names']}' is not active.")

    return active_special_collections
    
    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year)
        end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year)
        
        logging.info(f"Special collection: {special['collection_names']} start: {start_date} end: {end_date}")
        
        # Only include collections if they are within the date range (ignoring year)
        if start_date <= current_date <= end_date:
            logging.info(f"Special collection '{special['collection_names']}' is active.")
            active_special_collections.extend(special['collection_names'])
        else:
            logging.info(f"Special collection '{special['collection_names']}' is not active.")
    
    return active_special_collections

# Function to filter collections, prioritizing special collections, then categories, and finally random selections
def filter_collections(config, all_collections, active_special_collections, collection_limit, library_name):

    collections_to_pin = collections_to_pin if 'collections_to_pin' in locals() else []

    # Debug logging to check collection inclusion decisions
    print(f"[DEBUG] Checking collections for eligibility based on date and exclusion list...")
    for collection in collections_to_pin:
        print(f"[DEBUG] Collection: {collection} - Eligible for Pinning: {'YES' if collection in active_special_collections else 'NO'}")

    for collection in collections_to_pin:
        if collection in active_special_collections:
            # Confirm the collection's eligibility within date range again as a final check
            special_collection_active = False
            for special in config.get('special_collections', []):
                if collection in special['collection_names']:
                    start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year)
                    end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year)
                    if start_date <= current_date <= end_date:
                        special_collection_active = True
                        break
            if not special_collection_active:
                print(f"[DEBUG] Removing collection '{collection}' as it is outside of active date range.")
                collections_to_pin.remove(collection)

    # Perform a final validation of `collections_to_pin` to ensure no inactive special collections are included
    final_collections_to_pin = []
    for collection in collections_to_pin:
        if collection in active_special_collections:
            # Check date range for each collection one last time before adding
            for special in config.get('special_collections', []):
                if collection in special['collection_names']:
                    start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year)
                    end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year)
                    if start_date <= current_date <= end_date:
                        final_collections_to_pin.append(collection)
                        break
            else:
                print(f"[DEBUG] Collection '{collection}' removed in final cleanup as it is outside of date range.")
        else:
            final_collections_to_pin.append(collection)

    collections_to_pin = final_collections_to_pin  # Reassign filtered list

    exclusion_set = set(config.get('exclusion_list', []))
    collections_to_pin = []

    # Step 1: Pin active special collections within date range
    for special_collection in active_special_collections:
        matched_collections = [c for c in all_collections if c.title == special_collection and c.title not in exclusion_set]
        collections_to_pin.extend(matched_collections)

    # Step 2: If slots remain, add collections from configured categories
    remaining_slots = collection_limit - len(collections_to_pin)
    categories = config.get('categories', {}).get(library_name, {})
    if remaining_slots > 0:
        for category, collection_names in categories.items():
            category_collections = [c for c in all_collections if c.title in collection_names and c.title not in exclusion_set]
            if category_collections:
                selected_collection = random.choice(category_collections)
                collections_to_pin.append(selected_collection)
                remaining_slots -= 1
                if remaining_slots == 0:
                    break

    # Step 3: If slots still remain, add random collections
    available_collections = [c for c in all_collections if c.title not in exclusion_set and c.title not in active_special_collections]
    if remaining_slots > 0:
        random.shuffle(available_collections)
        collections_to_pin.extend(available_collections[:remaining_slots])

    logging.info(f"Final prioritized collections to pin for {library_name}: {[c.title for c in collections_to_pin]}")
    return collections_to_pin

def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies', 'TV Shows'])
    pinning_interval_seconds = config['pinning_interval'] * 60  # Convert from minutes to seconds

    selected_collections = load_selected_collections()
    current_day = datetime.now().strftime('%Y-%m-%d')
    if current_day not in selected_collections:
        selected_collections[current_day] = []

    while True:
        for library_name in library_names:
            collections_to_pin_for_library = config['number_of_collections_to_pin'].get(library_name, 0)
            
            logging.info(f"Processing library: {library_name} with {collections_to_pin_for_library} collections to pin.")

            # Unpin existing collections
            unpin_collections(plex, [library_name], exclusion_list)

            # Get special collections within active date range
            active_special_collections = get_active_special_collections(config)

            # Gather all collections in the current library
            all_collections = get_collections_from_all_libraries(plex, [library_name])

            # Filter collections based on date, categories, and any exclusions
            collections_to_pin = filter_collections(config, all_collections, active_special_collections, collections_to_pin_for_library, library_name)

            # Pin the collections
            if collections_to_pin:
                pin_collections(collections_to_pin, config)
                selected_collections[current_day].extend([c.title for c in collections_to_pin])
                save_selected_collections(selected_collections)
            else:
                logging.info(f"No collections available to pin for library: {library_name}.")

        # Wait before the next scheduled pinning
        logging.info(f"Scheduler set to change pinned collections every {config['pinning_interval']} minutes.")
        time.sleep(pinning_interval_seconds)

if __name__ == "__main__":
    main()
