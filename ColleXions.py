import random
import logging
import time
import json
import os
import sys
from plexapi.server import PlexServer
from datetime import datetime

# Configure logging to file with UTF-8 encoding for console output
LOG_FILE = 'collexions.log'
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
        
        if start_date <= current_date <= end_date:
            special_collections.extend(special['collection_names'])
    
    return special_collections

# Filter collections based on inclusion and exclusion
def filter_collections(config, all_collections, special_collections):
    inclusion_list = config.get('include_list', [])
    exclusion_list = config.get('exclusion_list', [])
    use_inclusion_list = config.get('use_inclusion_list', False)

    collections_to_pin = []

    # Filter by special collections first
    for special_collection in special_collections:
        matched_collections = [c for c in all_collections if c.title == special_collection]
        collections_to_pin.extend(matched_collections)

    # Remove special collections from available collections to avoid duplicates
    available_collections = [c for c in all_collections if c.title not in special_collections]

    # If using inclusion list
    if use_inclusion_list:
        logging.info(f"Using inclusion list: {inclusion_list}")
        available_collections = [c for c in available_collections if c.title in inclusion_list]
    else:
        # Exclude based on exclusion list
        logging.info(f"Using exclusion list: {exclusion_list}")
        available_collections = [c for c in available_collections if c.title not in exclusion_list]

    # Select additional collections if there are slots left to pin
    if len(collections_to_pin) < config['number_of_collections_to_pin']:
        remaining_slots = config['number_of_collections_to_pin'] - len(collections_to_pin)
        if available_collections:
            additional_collections = random.sample(available_collections, min(remaining_slots, len(available_collections)))
            collections_to_pin.extend(additional_collections)

    return collections_to_pin

# Main loop to randomly select and pin collections
def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies'])

    while True:
        # Step 1: Unpin currently pinned collections
        unpin_collections(plex, library_names, exclusion_list)

        # Step 2: Get special collections based on current date
        special_collections = get_special_collections(config)

        # Step 3: Get all collections from the libraries
        all_collections = get_collections_from_all_libraries(plex, library_names)

        # Step 4: Filter collections based on special collections, inclusion, and exclusion
        collections_to_pin = filter_collections(config, all_collections, special_collections)

        # Step 5: Pin the collections
        if collections_to_pin:
            pin_collections(collections_to_pin)
        else:
            logging.info("No collections available to pin.")

        logging.info(f"Scheduler set to change pinned collections every {config['pinning_interval'] / 60} minutes.")
        time.sleep(config['pinning_interval'])

if __name__ == "__main__":
    main()
