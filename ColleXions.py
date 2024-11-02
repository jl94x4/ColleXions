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
SELECTED_COLLECTIONS_FILE = 'selected_collections.json'

def load_selected_collections():
    if os.path.exists(SELECTED_COLLECTIONS_FILE):
        with open(SELECTED_COLLECTIONS_FILE, 'r', encoding='utf-8') as f:
            selected_collections = json.load(f)
    else:
        selected_collections = {}

    # Clean up entries older than 3 days
    current_date = datetime.now().date()
    cutoff_date = current_date - timedelta(days=3)
    selected_collections = {
        day: collections for day, collections in selected_collections.items()
        if datetime.strptime(day, '%Y-%m-%d').date() >= cutoff_date
    }
    return selected_collections

def save_selected_collections(selected_collections):
    current_date = datetime.now().date()
    cutoff_date = current_date - timedelta(days=3)
    selected_collections = {
        day: collections for day, collections in selected_collections.items()
        if datetime.strptime(day, '%Y-%m-%d').date() >= cutoff_date
    }
    with open(SELECTED_COLLECTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(selected_collections, f, ensure_ascii=False, indent=4)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        logging.error(f"Configuration file '{CONFIG_FILE}' not found.")
        raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found.")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

def connect_to_plex(config):
    logging.info("Connecting to Plex server...")
    plex = PlexServer(config['plex_url'], config['plex_token'])
    logging.info("Connected to Plex server successfully.")
    return plex

def get_collections_from_all_libraries(plex, library_names):
    all_collections = []
    for library_name in library_names:
        library = plex.library.section(library_name)
        collections = library.collections()
        all_collections.extend(collections)
    return all_collections

def pin_collections(collections, config):
    for collection in collections:
        try:
            logging.info(f"Attempting to pin collection: {collection.title}")
            hub = collection.visibility()
            hub.promoteHome()
            hub.promoteShared()
            message = f"INFO - Collection '**{collection.title}**' pinned successfully."
            logging.info(message)
            if 'discord_webhook_url' in config and config['discord_webhook_url']:
                send_discord_message(config['discord_webhook_url'], message)
        except Exception as e:
            logging.error(f"Error while pinning collection: {collection.title}. Error: {str(e)}")

def send_discord_message(webhook_url, message):
    data = {"content": message}
    response = requests.post(webhook_url, json=data)
    if response.status_code == 204:
        logging.info(f"Message sent to Discord: {message}")
    else:
        logging.error(f"Failed to send message to Discord. Status code: {response.status_code}")

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

from datetime import datetime, timedelta

def get_active_special_collections(config):
    current_date = datetime.now().date()  # Today's date without time component
    active_special_collections = []

    for special in config.get('special_collections', []):
        # Parse start and end dates as date objects for the current year
        start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year).date()
        end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year).date()

        # Adjust end date to be exclusive, so it includes only up to but not including the end date
        end_date_exclusive = end_date + timedelta(days=1)

        # Handle cross-year range by dividing it into two segments if needed
        if start_date > end_date:
            # Cross-year case: Collection is active if today is in the segment from start_date to Dec 31
            # or in the segment from Jan 1 to end_date in the next year
            if (start_date <= current_date <= datetime(current_date.year, 12, 31).date()) or \
               (datetime(current_date.year + 1, 1, 1).date() <= current_date < end_date_exclusive):
                active_special_collections.extend(special['collection_names'])
                logging.info(f"Collection '{special['collection_names']}' is active due to cross-year range.")
            else:
                logging.info(f"Collection '{special['collection_names']}' is NOT active (cross-year case).")
        else:
            # Standard date range within the same year
            if start_date <= current_date < end_date_exclusive:
                active_special_collections.extend(special['collection_names'])
                logging.info(f"Collection '{special['collection_names']}' is active for pinning.")
            else:
                logging.info(f"Collection '{special['collection_names']}' is NOT active (standard case).")

    logging.info(f"Final active special collections: {active_special_collections}")
    return active_special_collections


def filter_collections(config, all_collections, active_special_collections, collection_limit, library_name):
    exclusion_set = set(config.get('exclusion_list', []))
    special_collections_set = set(active_special_collections)  # Active special collections only
    all_special_collections = set()  # This will contain all special collections defined in config

    # Extract all special collections from the config, not just active ones
    for special in config.get('special_collections', []):
        all_special_collections.update(special['collection_names'])

    # Collections that should be excluded from random selection (inactive special collections + exclusion list)
    fully_excluded_collections = exclusion_set.union(all_special_collections - special_collections_set)

    collections_to_pin = []

    # Step 1: Pin only active special collections
    for special_collection in active_special_collections:
        matched_collections = [c for c in all_collections if c.title == special_collection and c.title not in exclusion_set]
        collections_to_pin.extend(matched_collections)
        logging.info(f"Added special collection '{special_collection}' to pinning list")

    # Step 2: If slots remain, add collections from configured categories, excluding all special collections
    remaining_slots = collection_limit - len(collections_to_pin)
    categories = config.get('categories', {}).get(library_name, {})
    if remaining_slots > 0:
        for category, collection_names in categories.items():
            category_collections = [c for c in all_collections if c.title in collection_names and c.title not in fully_excluded_collections]
            if category_collections:
                selected_collection = random.choice(category_collections)
                collections_to_pin.append(selected_collection)
                logging.info(f"Added '{selected_collection.title}' from category '{category}' to pinning list")
                remaining_slots -= 1
                if remaining_slots == 0:
                    break

    # Step 3: If slots still remain, add random collections excluding all special collections and excluded collections
    if remaining_slots > 0:
        available_collections = [c for c in all_collections if c.title not in fully_excluded_collections]
        logging.info(f"Available collections for random selection (fully excludes inactive special collections): {[c.title for c in available_collections]}")
        
        random.shuffle(available_collections)
        collections_to_pin.extend(available_collections[:remaining_slots])
        logging.info(f"Randomly selected collections to fill remaining slots: {[c.title for c in available_collections[:remaining_slots]]}")

    # Final debug log for collections pinned
    logging.info(f"Final collections selected for pinning in {library_name}: {[c.title for c in collections_to_pin]}")
    return collections_to_pin



def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies', 'TV Shows'])
    pinning_interval_seconds = config['pinning_interval'] * 60

    selected_collections = load_selected_collections()
    current_day = datetime.now().strftime('%Y-%m-%d')
    if current_day not in selected_collections:
        selected_collections[current_day] = []

    while True:
        for library_name in library_names:
            collections_to_pin_for_library = config['number_of_collections_to_pin'].get(library_name, 0)
            
            logging.info(f"Processing library: {library_name} with {collections_to_pin_for_library} collections to pin.")

            unpin_collections(plex, [library_name], exclusion_list)

            active_special_collections = get_active_special_collections(config)
            all_collections = get_collections_from_all_libraries(plex, [library_name])

            collections_to_pin = filter_collections(config, all_collections, active_special_collections, collections_to_pin_for_library, library_name)

            if collections_to_pin:
                pin_collections(collections_to_pin, config)
                selected_collections[current_day].extend([c.title for c in collections_to_pin])
                save_selected_collections(selected_collections)
            else:
                logging.info(f"No collections available to pin for library: {library_name}.")

        logging.info(f"Scheduler set to change pinned collections every {config['pinning_interval']} minutes.")
        time.sleep(pinning_interval_seconds)

if __name__ == "__main__":
    main()
