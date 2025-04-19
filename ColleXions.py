# (No changes to import section)
import random
import logging
import time
import json
import os
import sys
import re
import requests
from plexapi.server import PlexServer
from datetime import datetime, timedelta

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'collexions.log')

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

SELECTED_COLLECTIONS_FILE = 'selected_collections.json'


def load_selected_collections():
    if os.path.exists(SELECTED_COLLECTIONS_FILE):
        with open(SELECTED_COLLECTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_selected_collections(selected_collections):
    with open(SELECTED_COLLECTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(selected_collections, f, ensure_ascii=False, indent=4)


def get_recently_pinned_collections(selected_collections, config):
    cutoff_time = datetime.now() - timedelta(hours=config.get('repeat_block_hours', 12))
    recent_titles = set()

    for timestamp_str, titles in selected_collections.items():
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
            except ValueError:
                logging.warning(f"Unrecognized date format in selected_collections: {timestamp_str}")
                continue
        if timestamp >= cutoff_time:
            recent_titles.update(titles)

    return recent_titles


def is_regex_excluded(title, patterns):
    for pattern in patterns:
        if re.search(pattern, title, re.IGNORECASE):
            logging.info(f"Excluded by regex: '{title}' matched pattern '{pattern}'")
            return True
    return False


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as file:
            return json.load(file)
    logging.warning("Config file not found.")
    return {}


def connect_to_plex(config):
    logging.info("Connecting to Plex server...")
    plex = PlexServer(config['plex_url'], config['plex_token'])
    logging.info("Connected to Plex server successfully.")
    return plex


def get_collections_from_all_libraries(plex, library_names):
    all_collections = []
    for library_name in library_names:
        library = plex.library.section(library_name)
        all_collections.extend(library.collections())
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
            if config.get('discord_webhook_url'):
                send_discord_message(config['discord_webhook_url'], message)
        except Exception as e:
            logging.error(f"Error while pinning collection: {collection.title}. Error: {str(e)}")


def send_discord_message(webhook_url, message):
    data = {"content": message}
    response = requests.post(webhook_url, json=data)
    if response.status_code == 204:
        logging.info(f"Message sent to Discord: {message}")
    else:
        logging.error(f"Failed to send message to Discord. Status code: {response.status_code}, Response: {response.text}")


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


def get_active_special_collections(config):
    current_date = datetime.now().date()
    active_special_collections = []

    for special in config.get('special_collections', []):
        start_date = datetime.strptime(special['start_date'], '%m-%d').replace(year=current_date.year).date()
        end_date = datetime.strptime(special['end_date'], '%m-%d').replace(year=current_date.year).date()
        end_date_exclusive = end_date + timedelta(days=1)

        if start_date > end_date:
            if (start_date <= current_date <= datetime(current_date.year, 12, 31).date()) or \
               (datetime(current_date.year + 1, 1, 1).date() <= current_date < end_date_exclusive):
                active_special_collections.extend(special['collection_names'])
        else:
            if start_date <= current_date < end_date_exclusive:
                active_special_collections.extend(special['collection_names'])

    return active_special_collections


def get_fully_excluded_collections(config, active_special_collections):
    exclusion_set = set(config.get('exclusion_list', []))
    all_special_collections = set(
        col for special in config.get('special_collections', []) for col in special['collection_names']
    )
    return exclusion_set.union(all_special_collections - set(active_special_collections))


def select_from_categories(categories_config, all_collections, exclusion_set, remaining_slots, regex_patterns):
    collections_to_pin = []
    always_call = categories_config.pop('always_call', True)
    for category, collection_names in categories_config.items():
        category_collections = [
            c for c in all_collections
            if c.title in collection_names
            and c.title not in exclusion_set
            and not is_regex_excluded(c.title, regex_patterns)
        ]
        if category_collections and remaining_slots > 0:
            if always_call or random.choice([True, False]):
                selected_collection = random.choice(category_collections)
                collections_to_pin.append(selected_collection)
                logging.info(f"Added '{selected_collection.title}' from category '{category}' to pinning list")
                remaining_slots -= 1
    return collections_to_pin, remaining_slots


def fill_with_random_collections(random_collections, remaining_slots):
    collections_to_pin = []
    random_collections = random_collections[:]
    while remaining_slots > 0 and random_collections:
        selected_collection = random.choice(random_collections)
        collections_to_pin.append(selected_collection)
        logging.info(f"Added random collection '{selected_collection.title}' to pinning list")
        remaining_slots -= 1
        random_collections.remove(selected_collection)
    return collections_to_pin


def filter_collections(config, all_collections, active_special_collections, collection_limit, library_name, selected_collections):
    fully_excluded_collections = get_fully_excluded_collections(config, active_special_collections)
    recently_pinned = get_recently_pinned_collections(selected_collections, config)
    regex_patterns = config.get('regex_exclusion_patterns', [])

    total_exclusion_set = fully_excluded_collections.union(recently_pinned)

    collections_to_pin = []

    # Step 1: Special collections
    collections_to_pin.extend([
        c for c in all_collections
        if c.title in active_special_collections
        and c.title not in total_exclusion_set
        and not is_regex_excluded(c.title, regex_patterns)
    ])
    remaining_slots = collection_limit - len(collections_to_pin)

    # Step 2: Categories
    if remaining_slots > 0:
        categories_config = config.get('categories', {}).get(library_name, {})
        category_pins, remaining_slots = select_from_categories(categories_config, all_collections, total_exclusion_set, remaining_slots, regex_patterns)
        collections_to_pin.extend(category_pins)

    # Step 3: Random fill
    random_collections = [
        c for c in all_collections
        if c.title not in total_exclusion_set
        and c.title not in [c.title for c in collections_to_pin]
        and not is_regex_excluded(c.title, regex_patterns)
    ]
    collections_to_pin.extend(fill_with_random_collections(random_collections, remaining_slots))

    return collections_to_pin


def main():
    while True:
        config = load_config()
        plex = connect_to_plex(config)
        exclusion_list = config.get('exclusion_list', [])
        library_names = config.get('library_names', ['Movies', 'TV Shows'])
        pinning_interval_seconds = config['pinning_interval'] * 60

        selected_collections = load_selected_collections()
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        selected_collections[current_timestamp] = []

        for library_name in library_names:
            collections_to_pin_for_library = config['number_of_collections_to_pin'].get(library_name, 0)
            logging.info(f"Processing library: {library_name} with {collections_to_pin_for_library} collections to pin.")

            unpin_collections(plex, [library_name], exclusion_list)
            active_special_collections = get_active_special_collections(config)
            all_collections = get_collections_from_all_libraries(plex, [library_name])

            collections_to_pin = filter_collections(
                config,
                all_collections,
                active_special_collections,
                collections_to_pin_for_library,
                library_name,
                selected_collections
            )

            if collections_to_pin:
                pin_collections(collections_to_pin, config)
                selected_collections[current_timestamp].extend([c.title for c in collections_to_pin])
                save_selected_collections(selected_collections)
            else:
                logging.info(f"No collections available to pin for library: {library_name}.")

        logging.info(f"Sleeping for {config['pinning_interval']} minutes before next run.")
        time.sleep(pinning_interval_seconds)


if __name__ == "__main__":
    main()
