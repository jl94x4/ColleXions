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
CONFIG_FILE = '/root/collexions/config.json'

# File to store the selected collections per day
SELECTED_COLLECTIONS_FILE = '/root/collexions/selected_collections.json'

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
    current_date = datetime.now().date()
    current_month_day = (current_date.month, current_date.day)
    active_special_collections = []
    logging.info(f"Checking for special collections on date: {current_date}")
    
    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%m-%d')
        end_date = datetime.strptime(special['end_date'], '%m-%d')
        start_month_day = (start_date.month, start_date.day)
        end_month_day = (end_date.month, end_date.day)
        
        logging.info(f"Special collection: {special['collection_names']} start: {start_month_day} end: {end_month_day}")
        
        # Only include collections if they are within the date range (ignoring year)
        if start_month_day <= current_month_day <= end_month_day:
            logging.info(f"Special collection '{special['collection_names']}' is active.")
            active_special_collections.extend(special['collection_names'])
        else:
            logging.info(f"Special collection '{special['collection_names']}' is not active.")
    
    return active_special_collections
# Get special collections that should always be excluded from regular pinning when not active
def get_non_active_special_collections(config):
    current_date = datetime.now().date()
    non_active_special_collections = []
    logging.info(f"Checking for non-active special collections on date: {current_date}")
    
    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%m-%d').date()
        end_date = datetime.strptime(special['end_date'], '%m-%d').date()
        
        if not (start_date <= current_date <= end_date):
            non_active_special_collections.extend(special['collection_names'])
            logging.info(f"Special collection '{special['collection_names']}' is not active and will be excluded.")
    
    return non_active_special_collections

def filter_collections(config, all_collections, special_collections, collection_limit, library_name, selected_collections_last_week):
    categories = config.get('categories', {}).get(library_name, {})
    inclusion_set = set(config.get('include_list', []))
    exclusion_set = set(config.get('exclusion_list', []))
    use_inclusion_list = config.get('use_inclusion_list', False)
    collections_to_pin = []

    # Handle special collections (they should always be pinned)
    logging.info(f"Filtering collections with special collections: {special_collections}")
    special_collections_set = set(special_collections)
    for special_collection in special_collections_set:
        matched_collections = [c for c in all_collections if c.title == special_collection]
        collections_to_pin.extend(matched_collections)

    logging.info(f"Special collections pinned: {[c.title for c in collections_to_pin]}")

    # Use sets for faster lookups
    non_active_special_collections = get_non_active_special_collections(config)
    available_collections = [c for c in all_collections if c.title not in non_active_special_collections]

    # Reduce the number of checks by combining the inclusion/exclusion filtering in one loop
    categorized_collections = {category: [] for category in categories}
    for collection in available_collections:
        # Skip collections that were selected in the past 7 days
        if collection.title in selected_collections_last_week:
            continue
        
        if (use_inclusion_list and collection.title not in inclusion_set) or (collection.title in exclusion_set):
            continue
        
        for category, collection_names in categories.items():
            if collection.title in collection_names:
                categorized_collections[category].append(collection)

    logging.info(f"Categorized collections for {library_name}: {categorized_collections}")

    # Select one collection from each category, if available
    for category, collections in categorized_collections.items():
        if collections and len(collections_to_pin) < collection_limit:
            selected_collection = random.choice(collections)
            collections_to_pin.append(selected_collection)
            logging.info(f"Selected collection '{selected_collection.title}' from category '{category}'")
    
    # If the collections to pin are still fewer than the limit, pick random collections
    while len(collections_to_pin) < collection_limit:
        remaining_collections = [c for c in available_collections if c not in collections_to_pin]
        if not remaining_collections:
            break  # No more collections to add
        random_collection = random.choice(remaining_collections)
        collections_to_pin.append(random_collection)
        logging.info(f"Selected random collection '{random_collection.title}' to meet pinning limit")

    logging.info(f"Final collections to pin for {library_name}: {[c.title for c in collections_to_pin]}")
    return collections_to_pin




def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies', 'TV Shows'])
    pinning_interval_seconds = config['pinning_interval'] * 60  # Convert from minutes to seconds

    # Load already selected collections, cleaning up entries older than 7 days
    selected_collections = load_selected_collections()

    # Get current day and initialize selected collections for today
    current_day = datetime.now().strftime('%Y-%m-%d')
    if current_day not in selected_collections:
        selected_collections[current_day] = []

    # Gather all collections selected in the past 7 days
    selected_collections_last_week = []
    for day, collections in selected_collections.items():
        selected_collections_last_week.extend(collections)

    while True:
        for library_name in library_names:
            # Get the configured number of collections to pin for the current library
            collections_to_pin_for_library = config['number_of_collections_to_pin'].get(library_name, 0)
            
            logging.info(f"Processing library: {library_name} with {collections_to_pin_for_library} collections to pin.")
            
            # Step 1: Unpin currently pinned collections
            unpin_collections(plex, [library_name], exclusion_list)
            # Step 2: Get active special collections based on current date
            active_special_collections = get_active_special_collections(config)
            
            # Step 3: Get all collections from the current library
            all_collections = get_collections_from_all_libraries(plex, [library_name])
            
            # Step 4: Filter collections based on special collections and inclusion/exclusion
            collections_to_pin = filter_collections(config, all_collections, active_special_collections, collections_to_pin_for_library, library_name, selected_collections_last_week)
            
            # Step 5: Pin the collections
            if collections_to_pin:
                pin_collections(collections_to_pin, config)
                # Add newly selected collections to today's list
                selected_collections[current_day].extend([c.title for c in collections_to_pin])
                # Save selected collections while keeping the past week's data
                save_selected_collections(selected_collections)
            else:
                logging.info(f"No collections available to pin for library: {library_name}.")

        logging.info(f"Scheduler set to change pinned collections every {config['pinning_interval']} minutes.")
        time.sleep(pinning_interval_seconds)

if __name__ == "__main__":
    main()
