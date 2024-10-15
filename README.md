# ColleXions
ColleXions automates the process of pinning collections to your Plex home screen, making it easier to showcase your favorite content. With customizable features, it enhances your Plex experience by dynamically adjusting what is displayed, randomly.

## Key Features
- **Randomized Pinning:** ColleXions randomly selects collections to pin each cycle, ensuring that your home screen remains fresh and engaging. This randomness prevents the monotony of static collections, allowing users to discover new content easily.

- **Special Occasion Collections:** Automatically prioritizes collections linked to specific dates, making sure seasonal themes are highlighted when appropriate.

- **Exclusion List:** Users can specify collections to exclude from pinning, ensuring that only the most relevant or desired collections are featured.

- **Customizable Settings:** Users can easily adjust library names, pinning intervals, and the number of collections to pin, tailoring the experience to their preferences.

## Include & Exclude Collections

- **Exclude Collections:** The exclusion list allows you to specify collections that should never be pinned. These collections are "blacklisted," meaning that even if they are randomly selected or included in the special collections, they will be skipped, they will not be unpinned either.

- **Include Collections:** The inclusion list is the opposite of the exclusion list. It allows you to specify exactly which collections should be considered for pinning. This gives you control over which collections can be pinned, filtering the selection to only a few curated options. Make sure ```"use_inclusion_list": false,``` is set appropriately for your use case.

## Installation
Extract the files in the location you wish to run it from

Run ```pip install -r requirements.txt``` to install dependencies

Update the config.json file with your Plex URL, token, library names, and exclusion lists. 

Run ```python3 ColleXions.py```

**Please note: Pinning interval is in seconds, not minutes! In my example the field is set to 21600 which is 6 hours**

## Acknowledgments
Thanks to the PlexAPI library and the open-source community for their support.

## License
This project is licensed under the MIT License.
