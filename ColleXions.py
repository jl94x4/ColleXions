import random
import logging
import time
import json
import os
from plexapi.server import PlexServer
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

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
            hub = collection.visibility()  # Get the visibility hub for the collection
            hub.promoteHome()  # Pin to the home screen
            hub.promoteShared()  # Pin to friends' home screens
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
            if hub._promoted:  # Check if the collection is pinned
                hub.demoteHome()  # Unpin from the home screen
                hub.demoteShared()  # Unpin from friends' home screens
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
            special_collections.extend(special['collection_names'])  # Collect all special collection names
    
    return special_collections

# Main loop to randomly select and pin collections
def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies'])  # Fetch the library names from the config

    while True:
        unpin_collections(plex, library_names, exclusion_list)  # Unpin existing collections before pinning new ones
        
        special_collections = get_special_collections(config)
        logging.info(f"Special collections found: {special_collections}")  # Debugging line
        all_collections = get_collections_from_all_libraries(plex, library_names)

        collections_to_pin = []
        already_pinned_titles = set()  # Track collections that have been pinned

        # Pin special collections first
        if special_collections:
            logging.info("Found special collections to pin.")
            for collection_name in special_collections:
                matched_collections = [c for c in all_collections if c.title == collection_name]
                for collection in matched_collections:
                    if collection.title not in already_pinned_titles:
                        collections_to_pin.append(collection)
                        already_pinned_titles.add(collection.title)

        # If there are still collections to pin, pick randomly from all available (excluding special and duplicates)
        if len(collections_to_pin) < config['number_of_collections_to_pin']:
            remaining_slots = config['number_of_collections_to_pin'] - len(collections_to_pin)

            if config.get('use_inclusion_list', False):
                available_collections = [c for c in all_collections if c.title in config['include_list'] and c.title not in already_pinned_titles]
            else:
                available_collections = [c for c in all_collections if c.title not in already_pinned_titles and c.title not in exclusion_list]

            if available_collections:
                additional_collections = random.sample(available_collections, min(remaining_slots, len(available_collections)))
                collections_to_pin.extend(additional_collections)
                already_pinned_titles.update([c.title for c in additional_collections])

        # Pin the collections
        if collections_to_pin:
            pin_collections(collections_to_pin)
        else:
            logging.info("No collections available to pin.")

        logging.info(f"Scheduler set to change pinned collections every {config['pinning_interval'] / 60} minutes.")
        time.sleep(config['pinning_interval'])

if __name__ == "__main__":
    main()
