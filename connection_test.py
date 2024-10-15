from plexapi.server import PlexServer
import logging

# Configuration
URL = 'http://192.168.1.22:32400'  # Replace with your Plex server's IP and port
TOKEN = '8EUr6weXaTGnEUm2mHJi'  # Replace with your actual Plex token

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try
    # Attempt to connect to Plex server
    plex = PlexServer(URL, TOKEN)
    logging.info(Connected to Plex server successfully.)
    
    # List all libraries
    libraries = plex.library.sections()
    for library in libraries
        logging.info(fLibrary {library.title})
except Exception as e
    logging.error(fFailed to connect to Plex server {e})
