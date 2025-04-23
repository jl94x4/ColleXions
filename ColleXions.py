# --- Imports ---
import random
import logging
import time
import json
import os
import sys
import re
import requests
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, BadRequest
from datetime import datetime, timedelta

# --- Configuration & Constants ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'collexions.log')
SELECTED_COLLECTIONS_FILE = 'selected_collections.json'

# --- Setup Logging ---
if not os.path.exists(LOG_DIR):
    try: os.makedirs(LOG_DIR)
    except OSError as e: sys.stderr.write(f"Error creating log dir: {e}\n"); LOG_FILE = None

log_handlers = [logging.StreamHandler(sys.stdout)]
if LOG_FILE:
    try: log_handlers.append(logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'))
    except Exception as e: sys.stderr.write(f"Error setting up file log: {e}\n")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s',
    handlers=log_handlers
)

# --- Functions ---

def load_selected_collections():
    """Loads the history of previously pinned collections."""
    if os.path.exists(SELECTED_COLLECTIONS_FILE):
        try:
            with open(SELECTED_COLLECTIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f);
                if isinstance(data, dict): return data
                else: logging.error(f"Invalid format in {SELECTED_COLLECTIONS_FILE}. Resetting."); return {}
        except json.JSONDecodeError: logging.error(f"Error decoding {SELECTED_COLLECTIONS_FILE}. Resetting."); return {}
        except Exception as e: logging.error(f"Error loading {SELECTED_COLLECTIONS_FILE}: {e}. Resetting."); return {}
    return {}

def save_selected_collections(selected_collections):
    """Saves the updated history of pinned collections."""
    try:
        with open(SELECTED_COLLECTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(selected_collections, f, ensure_ascii=False, indent=4)
    except Exception as e: logging.error(f"Error saving {SELECTED_COLLECTIONS_FILE}: {e}")

def get_recently_pinned_collections(selected_collections, config):
    """Gets titles of non-special collections pinned within the repeat_block_hours window."""
    # Note: This function now only considers titles saved in the history file,
    # which (with the main loop change) will exclude special collections.
    repeat_block_hours = config.get('repeat_block_hours', 12)
    if not isinstance(repeat_block_hours, (int, float)) or repeat_block_hours <= 0:
        logging.warning(f"Invalid 'repeat_block_hours', defaulting 12."); repeat_block_hours = 12
    cutoff_time = datetime.now() - timedelta(hours=repeat_block_hours)
    recent_titles = set()
    timestamps_to_keep = {}
    logging.info(f"Checking history since {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} for recently pinned non-special items")
    for timestamp_str, titles in list(selected_collections.items()):
        if not isinstance(titles, list): logging.warning(f"Cleaning invalid history: {timestamp_str}"); selected_collections.pop(timestamp_str, None); continue
        try:
            try: timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            except ValueError: timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
            if timestamp >= cutoff_time:
                valid_titles = {t for t in titles if isinstance(t, str)}; recent_titles.update(valid_titles)
                timestamps_to_keep[timestamp_str] = titles # Keep this entry in the temporary dict
        except ValueError: logging.warning(f"Cleaning invalid date format: '{timestamp_str}'."); selected_collections.pop(timestamp_str, None)
        except Exception as e: logging.error(f"Cleaning problematic history '{timestamp_str}': {e}."); selected_collections.pop(timestamp_str, None)

    # Update the main selected_collections dict to only contain recent entries
    keys_to_remove = set(selected_collections.keys()) - set(timestamps_to_keep.keys())
    if keys_to_remove:
         logging.info(f"Removing {len(keys_to_remove)} old entries from history file.")
         for key in keys_to_remove: selected_collections.pop(key, None)
         save_selected_collections(selected_collections) # Save cleaned history immediately

    if recent_titles:
        logging.info(f"Recently pinned non-special collections (excluded): {', '.join(sorted(list(recent_titles)))}")
    return recent_titles # This set now only contains non-special recently pinned items

def is_regex_excluded(title, patterns):
    """Checks if a title matches any regex pattern."""
    if not patterns or not isinstance(patterns, list): return False
    try:
        for pattern in patterns:
            if not isinstance(pattern, str) or not pattern: continue
            if re.search(pattern, title, re.IGNORECASE): logging.info(f"Excluding '{title}' (regex: '{pattern}')"); return True
    except re.error as e: logging.error(f"Invalid regex '{pattern}': {e}"); return False
    except Exception as e: logging.error(f"Regex error for '{title}', pattern '{pattern}': {e}"); return False
    return False

def load_config():
    """Loads configuration from config.json, exits on critical errors."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f: # Use f
                config_data = json.load(f) # Use f
                if not isinstance(config_data, dict): raise ValueError("Config not JSON object.")
                return config_data
        except Exception as e: logging.critical(f"CRITICAL: Error load/parse {CONFIG_PATH}: {e}. Exit."); sys.exit(1)
    else: logging.critical(f"CRITICAL: Config not found {CONFIG_PATH}. Exit."); sys.exit(1)

def connect_to_plex(config):
    """Connects to Plex server, returns PlexServer object or None."""
    try:
        logging.info("Connecting to Plex server...")
        plex_url, plex_token = config.get('plex_url'), config.get('plex_token')
        if not isinstance(plex_url, str) or not plex_url or not isinstance(plex_token, str) or not plex_token:
            raise ValueError("Missing/invalid 'plex_url'/'plex_token'")
        plex = PlexServer(plex_url, plex_token, timeout=60)
        logging.info(f"Connected to Plex server '{plex.friendlyName}' successfully.")
        return plex
    except ValueError as e: logging.error(f"Config error for Plex: {e}"); return None
    except Exception as e: logging.error(f"Failed to connect to Plex: {e}"); return None

def get_collections_from_all_libraries(plex, library_names):
    """Fetches all collection objects from the specified library names."""
    all_collections = []
    if not plex or not library_names: return all_collections
    for library_name in library_names:
        if not isinstance(library_name, str): logging.warning(f"Invalid lib name: {library_name}"); continue
        try:
            library = plex.library.section(library_name)
            collections_in_library = library.collections()
            logging.info(f"Found {len(collections_in_library)} collections in '{library_name}'.")
            all_collections.extend(collections_in_library)
        except NotFound: logging.error(f"Library '{library_name}' not found.")
        except Exception as e: logging.error(f"Error fetching from '{library_name}': {e}")
    return all_collections

# --- MODIFIED FUNCTION ---
def pin_collections(collections, config):
    """Pins the provided list of collections and sends individual Discord notifications."""
    if not collections:
        logging.info("Pin list is empty.")
        return
    webhook_url = config.get('discord_webhook_url')
    for collection in collections:
        coll_title = getattr(collection, 'title', 'Untitled')
        try:
            if not hasattr(collection, 'visibility'):
                logging.warning(f"Skip invalid collection object: '{coll_title}'.")
                continue

            # --- Get item count ---
            try:
                item_count = collection.childCount
            except Exception as e:
                logging.warning(f"Could not get item count for '{coll_title}': {e}")
                item_count = "Unknown" # Fallback if count fails

            logging.info(f"Attempting to pin: '{coll_title}'")
            hub = collection.visibility()
            hub.promoteHome()
            hub.promoteShared()

            # --- Create messages (plain for log, Markdown for Discord) ---
            log_message = f"INFO - Collection '{coll_title} - {item_count} Items' pinned successfully."
            discord_message = f"INFO - Collection '**{coll_title} - {item_count} Items**' pinned successfully."
            # --- End modification ---

            logging.info(log_message) # Log the plain message
            if webhook_url:
                # Send the Markdown formatted message to Discord
                send_discord_message(webhook_url, discord_message)
        except Exception as e:
            logging.error(f"Error pinning '{coll_title}': {e}")
# --- END MODIFIED FUNCTION ---

def send_discord_message(webhook_url, message):
    """Sends a message to the specified Discord webhook URL."""
    if not webhook_url or not isinstance(webhook_url, str): return
    data = {"content": message}
    try:
        response = requests.post(webhook_url, json=data, timeout=10)
        response.raise_for_status()
        logging.info(f"Discord msg sent (Status: {response.status_code})")
    except requests.exceptions.RequestException as e: logging.error(f"Failed send to Discord: {e}")
    except Exception as e: logging.error(f"Discord message error: {e}")

def unpin_collections(plex, library_names, exclusion_list):
    """Unpins currently promoted collections, respecting exclusions, with enhanced error logging."""
    if not plex: return
    logging.info(f"Starting unpin for: {library_names} (Excluding: {exclusion_list})")
    unpinned_count = 0
    exclusion_set = set(exclusion_list) if isinstance(exclusion_list, list) else set()
    for library_name in library_names:
        try:
            library = plex.library.section(library_name)
            collections_in_library = library.collections()
            logging.info(f"Checking {len(collections_in_library)} collections in '{library_name}'.")
            for collection in collections_in_library:
                coll_title = getattr(collection, 'title', 'Untitled')
                if coll_title in exclusion_set: logging.info(f"Skip unpin excluded: '{coll_title}'"); continue
                try:
                    hub = collection.visibility()
                    if hub._promoted:
                        logging.info(f"Attempting unpin: '{coll_title}'")
                        try:
                            hub.demoteHome(); hub.demoteShared()
                            logging.info(f"Unpinned '{coll_title}' OK.")
                            unpinned_count += 1
                        except Exception as demote_error: logging.error(f"Failed demote for '{coll_title}': {demote_error}")
                except Exception as vis_error: logging.error(f"Error check visibility for '{coll_title}': {vis_error}")
        except NotFound: logging.error(f"Lib '{library_name}' not found for unpin.")
        except Exception as e: logging.error(f"Error during unpin for '{library_name}': {e}")
    logging.info(f"Unpinning complete. Unpinned {unpinned_count} collections.")

def get_active_special_collections(config):
    """Determines which 'special' collections are active based on current date."""
    current_date = datetime.now().date()
    active_titles = []
    special_configs = config.get('special_collections', [])
    if not isinstance(special_configs, list): logging.warning("'special_collections' not list."); return []
    for special in special_configs:
        if not isinstance(special, dict) or not all(k in special for k in ['start_date', 'end_date', 'collection_names']): continue
        s_date, e_date, names = special.get('start_date'), special.get('end_date'), special.get('collection_names')
        if not isinstance(names, list) or not s_date or not e_date: continue
        try:
            start = datetime.strptime(s_date, '%m-%d').replace(year=current_date.year).date()
            end = datetime.strptime(e_date, '%m-%d').replace(year=current_date.year).date()
            end_excl = end + timedelta(days=1)
            is_active = (start <= current_date < end_excl) if start <= end else (start <= current_date or current_date < end_excl)
            if is_active: active_titles.extend(n for n in names if isinstance(n, str))
        except ValueError: logging.error(f"Invalid date format in special: {special}. Use MM-DD.")
        except Exception as e: logging.error(f"Error process special {names}: {e}")
    unique_active = list(set(active_titles))
    if unique_active: logging.info(f"Active special collections: {unique_active}")
    return unique_active

def get_fully_excluded_collections(config, active_special_collections):
    """Combines explicit exclusions and inactive special collections."""
    exclusion_raw = config.get('exclusion_list', []); exclusion_set = set(n for n in exclusion_raw if isinstance(n, str))
    all_special = get_all_special_collection_names(config) # Use helper function
    inactive = all_special - set(active_special_collections)
    if inactive: logging.info(f"Excluding inactive special collections by title: {inactive}")
    combined = exclusion_set.union(inactive)
    logging.info(f"Total title exclusions (explicit + inactive special): {combined or 'None'}")
    return combined

# --- NEW HELPER FUNCTION ---
def get_all_special_collection_names(config):
    """Returns a set of all collection names defined in special_collections config."""
    all_special_titles = set()
    special_configs = config.get('special_collections', [])
    if not isinstance(special_configs, list):
        logging.warning("'special_collections' in config is not a list. Cannot identify all special titles.")
        return all_special_titles # Return empty set

    for special in special_configs:
        # Check structure before accessing keys
        if isinstance(special, dict) and 'collection_names' in special and isinstance(special['collection_names'], list):
             # Add all valid string names from this special entry
             all_special_titles.update(name for name in special['collection_names'] if isinstance(name, str))
        else:
            logging.warning(f"Skipping invalid entry when getting all special names: {special}")

    if all_special_titles:
        logging.info(f"Identified {len(all_special_titles)} unique titles defined across all special_collections entries.")
    return all_special_titles
# --- END NEW HELPER FUNCTION ---


def select_from_categories(categories_config, all_collections, exclusion_set, remaining_slots, regex_patterns):
    """Selects items from categories based on config (version from user script)."""
    # This function now relies on the exclusion_set passed in, which includes recently pinned NON-SPECIAL items
    collections_to_pin = []
    config_dict = categories_config if isinstance(categories_config, dict) else {}
    always_call = config_dict.pop('always_call', True)
    category_items = config_dict.items()
    processed_titles_in_this_step = set()
    for category, collection_names in category_items:
        if remaining_slots <= 0: break
        if not isinstance(collection_names, list): continue
        potential_pins = [
            c for c in all_collections
            if getattr(c, 'title', None) in collection_names
            and getattr(c, 'title', None) not in exclusion_set # Checks against combined exclusions
            and not is_regex_excluded(getattr(c, 'title', ''), regex_patterns)
            and getattr(c, 'title', None) not in processed_titles_in_this_step
        ]
        if potential_pins:
            if always_call or random.choice([True, False]):
                selected = random.choice(potential_pins)
                collections_to_pin.append(selected)
                processed_titles_in_this_step.add(selected.title)
                exclusion_set.add(selected.title) # Add to exclusion for this cycle
                logging.info(f"Added '{selected.title}' from category '{category}'")
                remaining_slots -= 1
    if isinstance(categories_config, dict): categories_config['always_call'] = always_call
    return collections_to_pin, remaining_slots


def fill_with_random_collections(random_collections_pool, remaining_slots):
    """Fills remaining slots with random choices (version from user script)."""
    # Assumes random_collections_pool is already filtered
    collections_to_pin = []
    available = random_collections_pool[:]
    if not available: logging.info("No items left for random."); return collections_to_pin
    random.shuffle(available)
    num = min(remaining_slots, len(available))
    logging.info(f"Selecting up to {num} random collections from {len(available)}.")
    selected = available[:num]
    collections_to_pin.extend(selected)
    for c in selected: logging.info(f"Added random collection '{getattr(c, 'title', 'Untitled')}'")
    return collections_to_pin


def filter_collections(config, all_collections, active_special_collections, collection_limit, library_name, selected_collections):
    """Filters collections and selects pins, using config threshold."""
    min_items_threshold = config.get('min_items_for_pinning', 10) # Reads from config
    logging.info(f"Filtering: Min items required = {min_items_threshold}")

    # Get exclusion sets:
    # Note: get_recently_pinned_collections now only returns non-special items based on modified history
    fully_excluded_collections = get_fully_excluded_collections(config, active_special_collections)
    recently_pinned_non_special = get_recently_pinned_collections(selected_collections, config)
    regex_patterns = config.get('regex_exclusion_patterns', [])
    # Combine title exclusions: explicit, inactive special, recently pinned non-special
    title_exclusion_set = fully_excluded_collections.union(recently_pinned_non_special)

    eligible_collections = []
    logging.info(f"Starting with {len(all_collections)} collections in '{library_name}'.")
    for c in all_collections:
        coll_title = getattr(c, 'title', None);
        if not coll_title: continue
        # Check exclusions that apply to ALL types (including special)
        if coll_title in fully_excluded_collections: continue # Explicit list or inactive special
        if is_regex_excluded(coll_title, regex_patterns): continue
        try:
            # Use childCount attribute directly
            if c.childCount < min_items_threshold:
                logging.info(f"Excluding '{coll_title}' (low count: {c.childCount})")
                continue
        except AttributeError: # Handle cases where childCount might not exist
             logging.warning(f"Excluding '{coll_title}' (AttributeError getting childCount)")
             continue
        except Exception as e: # Catch other potential errors
             logging.warning(f"Excluding '{coll_title}' (count error: {e})")
             continue


        # Check recency exclusion ONLY if it's NOT an active special collection
        if coll_title not in active_special_collections and coll_title in recently_pinned_non_special:
             logging.info(f"Excluding '{coll_title}' (recently pinned non-special item).")
             continue

        # If all checks passed, it's eligible for selection based on priority
        eligible_collections.append(c)

    logging.info(f"Found {len(eligible_collections)} eligible collections for selection priority.")

    collections_to_pin = []; pinned_titles = set(); remaining = collection_limit

    # Step 1: Special (These have already passed size/regex/explicit/inactive checks)
    # Recency check was skipped for them above.
    specials = [c for c in eligible_collections if c.title in active_special_collections][:remaining]
    collections_to_pin.extend(specials); pinned_titles.update(c.title for c in specials); remaining -= len(specials)
    if specials: logging.info(f"Added {len(specials)} special: {[c.title for c in specials]}. Left: {remaining}")

    # Step 2: Categories (Items here have passed all checks including recency)
    if remaining > 0:
        cat_conf = config.get('categories', {}).get(library_name, {});
        # Pass only items not already selected as special
        eligible_cat = [c for c in eligible_collections if c.title not in pinned_titles]
        # Exclusions passed to select_from_categories are now just for preventing category overlap within the step
        # as main exclusions were already applied to create eligible_collections
        cat_pins, remaining = select_from_categories(cat_conf, eligible_cat, pinned_titles.copy(), remaining, regex_patterns) # Pass copy of pinned_titles
        collections_to_pin.extend(cat_pins); pinned_titles.update(c.title for c in cat_pins)
        if cat_pins: logging.info(f"Added {len(cat_pins)} from categories. Left: {remaining}")

    # Step 3: Random (Items here have passed all checks including recency)
    if remaining > 0:
        eligible_rand = [c for c in eligible_collections if c.title not in pinned_titles]
        rand_pins = fill_with_random_collections(eligible_rand, remaining)
        collections_to_pin.extend(rand_pins)
        # No need to update pinned_titles here, it's the last step

    logging.info(f"Final list for '{library_name}': {[c.title for c in collections_to_pin]}")
    return collections_to_pin


# --- Main Function (UPDATED) ---
def main():
    """Main execution loop."""
    logging.info("Starting Collexions Script")
    while True:
        run_start = time.time()
        config = load_config()
        if not all(k in config for k in ['plex_url', 'plex_token', 'pinning_interval']):
             logging.critical("Config essentials missing. Exit."); sys.exit(1)

        pin_interval = config.get('pinning_interval', 60);
        if not isinstance(pin_interval, (int, float)) or pin_interval <= 0: pin_interval = 60
        sleep_sec = pin_interval * 60

        plex = connect_to_plex(config)
        if not plex:
            logging.error(f"Plex connection failed. Retrying in {pin_interval} min.")
        else:
            exclusion_list = config.get('exclusion_list', []);
            if not isinstance(exclusion_list, list): exclusion_list = []
            library_names = config.get('library_names', [])
            if not isinstance(library_names, list): library_names = []
            collections_per_library_config = config.get('number_of_collections_to_pin', {})
            if not isinstance(collections_per_library_config, dict): collections_per_library_config = {}

            selected_collections = load_selected_collections() # Load current history
            current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # Don't pre-initialize timestamp entry, add only if non-specials are pinned
            newly_pinned_titles_this_run = [] # Track all pins for this run

            # --- Get all special titles ONCE per cycle ---
            all_special_titles = get_all_special_collection_names(config)
            # -------------------------------------------

            for library_name in library_names:
                library_process_start = time.time()
                if not isinstance(library_name, str): logging.warning(f"Skipping invalid library name: {library_name}"); continue

                pin_limit = collections_per_library_config.get(library_name, 0);
                if not isinstance(pin_limit, int) or pin_limit < 0: pin_limit = 0
                if pin_limit == 0: logging.info(f"Skip '{library_name}': 0 limit."); continue

                logging.info(f"Processing '{library_name}' (Limit: {pin_limit})")
                unpin_collections(plex, [library_name], exclusion_list)
                active_specials = get_active_special_collections(config)
                all_colls = get_collections_from_all_libraries(plex, [library_name])
                if not all_colls: logging.info(f"No collections in '{library_name}'."); continue

                colls_to_pin = filter_collections(config, all_colls, active_specials, pin_limit, library_name, selected_collections)
                if colls_to_pin:
                    pin_collections(colls_to_pin, config) # Calls the modified function
                    # Add ALL pinned titles to the list for THIS run's tracking
                    newly_pinned_titles_this_run.extend([c.title for c in colls_to_pin if hasattr(c, 'title')])
                else: logging.info(f"No collections selected for '{library_name}'.")
                logging.info(f"Finished '{library_name}' in {time.time() - library_process_start:.2f}s.")

            # --- Modified History Update Logic ---
            if newly_pinned_titles_this_run:
                 unique_new_pins_all = set(newly_pinned_titles_this_run)
                 # Filter out special collections before saving to history
                 non_special_pins_for_history = {
                     title for title in unique_new_pins_all
                     if title not in all_special_titles # Use the set fetched earlier
                 }
                 # Only update history file if there were non-special items pinned
                 if non_special_pins_for_history:
                      history_entry = sorted(list(non_special_pins_for_history))
                      selected_collections[current_timestamp] = history_entry
                      save_selected_collections(selected_collections)
                      logging.info(f"Updated history for {current_timestamp} with {len(history_entry)} non-special items.")
                      if len(unique_new_pins_all) > len(non_special_pins_for_history):
                          logging.info(f"Note: {len(unique_new_pins_all) - len(non_special_pins_for_history)} special collection(s) were pinned but not added to recency history.")
                 else:
                      logging.info("Only special collections were pinned this cycle. History not updated for recency blocking.")
            else:
                 logging.info("Nothing pinned this cycle, history not updated.")
            # --- End Modified History Update ---

        run_end = time.time()
        logging.info(f"Cycle finished in {run_end - run_start:.2f} seconds.")
        logging.info(f"Sleeping for {pin_interval} minutes...")
        try: time.sleep(sleep_sec)
        except KeyboardInterrupt: logging.info("Script interrupted. Exiting."); break

# --- Script Entry Point ---
if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: logging.info("Script terminated by user.")
    except Exception as e: logging.critical(f"UNHANDLED EXCEPTION: {e}", exc_info=True); sys.exit(1)
