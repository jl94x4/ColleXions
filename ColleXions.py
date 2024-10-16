import random
import logging
import time
import json
import os
import sys
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
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),  # Overwrites the log file
        logging.StreamHandler(sys.stdout)  # Use standard output for console
    ]
)

# Configuration file path
CONFIG_FILE = 'config.json'

# Load configuration from the JSON file
def load_config():
    if not os.path.exists(CONFIG_FILE):
        logging.error(f"Configuration file '{CONFIG_FILE}' not found.")
        raise FileNotFoundError(f"Configuration file '{CONFIG_FILE}' not found.")
    
    with open(CONFIG_FILE, 'r') as f:
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
def pin_collections(collections):
    for collection in collections:
        try:
            logging.info(f"Attempting to pin collection: {collection.title}")
            hub = collection.visibility()
            hub.promoteHome()
            hub.promoteShared()
            logging.info(f"Collection '{collection.title}' pinned successfully to Home and Friends' Home screens.")
        except Exception as e:
            logging.error(f"Unexpected error while pinning collection: {collection.title}. Error: {str(e)}")

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

# Check for special scheduled collections
def get_special_collections(config):
    current_date = datetime.now().date()
    special_collections = []
    
    logging.info(f"Checking for special collections on date: {current_date}")
    
    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(special['end_date'], '%Y-%m-%d').date()
        
        logging.info(f"Checking special collection '{special['collection_names']}' from {start_date} to {end_date}")
        
        if start_date <= current_date <= end_date:
            special_collections.extend(special['collection_names'])
            logging.info(f"Adding special collection(s): {special['collection_names']}")
        else:
            logging.info(f"Current date is outside the range for collection '{special['collection_names']}'.")

    return special_collections

# Filter collections based on inclusion and exclusion
def filter_collections(config, all_collections):
    inclusion_list = config.get('include_list', [])
    exclusion_list = config.get('exclusion_list', [])
    use_inclusion_list = config.get('use_inclusion_list', False)

    collections_to_pin = []

    # First, ensure we only consider special collections that are valid for pinning
    valid_special_collections = get_special_collections(config)

    # Filter by valid special collections first
    for special_collection in valid_special_collections:
        matched_collections = [c for c in all_collections if c.title == special_collection]
        collections_to_pin.extend(matched_collections)

    # Remove pinned special collections from available collections to avoid duplicates
    available_collections = [c for c in all_collections if c.title not in valid_special_collections]

    # If using inclusion list
    if use_inclusion_list:
        logging.info(f"Using inclusion list: {inclusion_list}")
        available_collections = [c for c in available_collections if c.title in inclusion_list]
    else:
        # Exclude based on exclusion list
        logging.info(f"Using exclusion list: {exclusion_list}")
        available_collections = [c for c in available_collections if c.title not in exclusion_list]

    # Select additional collections if there are slots left to pin
    remaining_slots = config['number_of_collections_to_pin'] - len(collections_to_pin)

    if remaining_slots > 0 and available_collections:
        # Allow collections on the exclusion list if they are valid special collections
        additional_collections = [c for c in all_collections if c.title in valid_special_collections or c.title not in exclusion_list]
        if additional_collections:
            additional_collections = random.sample(additional_collections, min(remaining_slots, len(additional_collections)))
            collections_to_pin.extend(additional_collections)

    # Ensure the number of collections pinned does not exceed the defined limit
    return collections_to_pin[:config['number_of_collections_to_pin']]

# Main loop to randomly select and pin collections
def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies'])

    while True:
        # Step 1: Unpin currently pinned collections
        unpin_collections(plex, library_names, exclusion_list)

        # Step 2: Get all collections from the libraries
        all_collections = get_collections_from_all_libraries(plex, library_names)

        # Step 3: Filter collections based on special collections, inclusion, and exclusion
        collections_to_pin = filter_collections(config, all_collections)

        # Step 4: Pin the collections
        if collections_to_pin:
            pin_collections(collections_to_pin)
        else:
            logging.info("No collections available to pin.")

        logging.info(f"Scheduler set to change pinned collections every {config['pinning_interval'] / 60} minutes.")
        time.sleep(config['pinning_interval'])

if __name__ == "__main__":
    main()
