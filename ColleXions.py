import random
import logging
import time
import json
import os
import sys
import requests
from plexapi.server import PlexServer
from datetime import datetime

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
    active_special_collections = []
    logging.info(f"Checking for active special collections on date: {current_date}")
    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(special['end_date'], '%Y-%m-%d').date()
        
        # Only include special collections if they are within the date range
        if start_date <= current_date <= end_date:
            active_special_collections.extend(special['collection_names'])
            logging.info(f"Special collection '{special['collection_names']}' is active (start: {start_date}, end: {end_date}).")
        else:
            logging.info(f"Special collection '{special['collection_names']}' is not active (start: {start_date}, end: {end_date}).")
    
    return active_special_collections

# Get special collections that should always be excluded from regular pinning when not active
def get_non_active_special_collections(config):
    current_date = datetime.now().date()
    non_active_special_collections = []
    logging.info(f"Checking for non-active special collections on date: {current_date}")
    
    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(special['end_date'], '%Y-%m-%d').date()
        
        if not (start_date <= current_date <= end_date):
            non_active_special_collections.extend(special['collection_names'])
            logging.info(f"Special collection '{special['collection_names']}' is not active and will be excluded.")
    
    return non_active_special_collections

# Filter collections based on inclusion and exclusion and date ranges
def filter_collections(config, all_collections, special_collections):
    inclusion_list = config.get('include_list', [])
    exclusion_list = config.get('exclusion_list', [])
    use_inclusion_list = config.get('use_inclusion_list', False)
    collections_to_pin = []

    # Handle special collections separately
    logging.info(f"Filtering collections with special collections: {special_collections}")
    for special_collection in special_collections:
        matched_collections = [c for c in all_collections if c.title == special_collection]
        collections_to_pin.extend(matched_collections)

    logging.info(f"Collections to pin after adding special collections: {[c.title for c in collections_to_pin]}")

    # Exclude non-active special collections from regular pinning
    non_active_special_collections = get_non_active_special_collections(config)
    available_collections = [c for c in all_collections if c.title not in non_active_special_collections]

    # Apply inclusion or exclusion logic
    if use_inclusion_list:
        logging.info(f"Using inclusion list: {inclusion_list}")
        available_collections = [c for c in available_collections if c.title in inclusion_list]
    else:
        logging.info(f"Using exclusion list: {exclusion_list}")
        available_collections = [c for c in available_collections if c.title not in exclusion_list]
    
    # Select additional collections if necessary
    if len(collections_to_pin) < config['number_of_collections_to_pin']:
        remaining_slots = config['number_of_collections_to_pin'] - len(collections_to_pin)
        if available_collections:
            additional_collections = random.sample(available_collections, min(remaining_slots, len(available_collections)))
            collections_to_pin.extend(additional_collections)

    logging.info(f"Final collections to pin: {[c.title for c in collections_to_pin]}")
    return collections_to_pin

# Main loop to randomly select and pin collections
def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies'])
    pinning_interval_seconds = config['pinning_interval'] * 60  # Convert from minutes to seconds
    while True:
        # Step 1: Unpin currently pinned collections
        unpin_collections(plex, library_names, exclusion_list)
        # Step 2: Get active special collections based on current date
        active_special_collections = get_active_special_collections(config)
        # Step 3: Get all collections from the libraries
        all_collections = get_collections_from_all_libraries(plex, library_names)
        # Step 4: Filter collections based on special collections and inclusion/exclusion
        collections_to_pin = filter_collections(config, all_collections, active_special_collections)
        # Step 5: Pin the collections
        if collections_to_pin:
            pin_collections(collections_to_pin, config)
        else:
            logging.info("No collections available to pin.")
        logging.info(f"Scheduler set to change pinned collections every {config['pinning_interval']} minutes.")
        time.sleep(pinning_interval_seconds)

if __name__ == "__main__":
    main()
