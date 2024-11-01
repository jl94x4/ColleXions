# Ensure logging configuration and essential imports remain the same
import random
import logging
import time
import json
import os
import sys
import requests
from plexapi.server import PlexServer
from datetime import datetime, timedelta

# Define log file path, loading configuration, and other setup code remains as per original script

# Function to retrieve active special collections within date range
def get_active_special_collections(config):
    current_date = datetime.now().date()
    active_special_collections = []
    logging.info(f"Checking for active special collections on {current_date}")

    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year)
        end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year)

        # If current date is within range, add to active special collections
        if start_date <= current_date <= end_date:
            active_special_collections.extend(special['collection_names'])
            logging.info(f"Active special collection: {special['collection_names']} (from {start_date} to {end_date})")

    return active_special_collections

# Function to filter collections for pinning
def filter_collections(config, all_collections, active_special_collections, collection_limit, library_name):
    exclusion_set = set(config.get('exclusion_list', []))
    collections_to_pin = []

    # Step 1: Pin active special collections within date range
    for special_collection in active_special_collections:
        matched_collections = [c for c in all_collections if c.title == special_collection]
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

    logging.info(f"Final collections to pin for {library_name}: {[c.title for c in collections_to_pin]}")
    return collections_to_pin

# Original main function, including unchanged configuration loading, logging, and scheduling logic
def main():
    config = load_config()
    plex = connect_to_plex(config)
    exclusion_list = config.get('exclusion_list', [])
    library_names = config.get('library_names', ['Movies', 'TV Shows'])
    pinning_interval_seconds = config['pinning_interval'] * 60  # Convert minutes to seconds

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
        logging.info(f"Scheduler set to run every {config['pinning_interval']} minutes.")
        time.sleep(pinning_interval_seconds)

if __name__ == "__main__":
    main()
