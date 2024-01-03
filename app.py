from flask import Flask, request
from plexapi.server import PlexServer
from urllib.parse import urlparse
from collections import deque
import os, sys, time

# Cache for deleted episodes (episode identifier, timestamp)
deleted_episodes = deque(maxlen=100)

app = Flask(__name__)

def get_env_variable(var_name, required=True):
    value = os.getenv(var_name)
    if required and not value:
        app.logger.info(f"Error: The {var_name} environment variable is required.")
        sys.exit(1)
    return value

def is_valid_url(url):
    parsed = urlparse(url)
    return all([parsed.scheme, parsed.netloc])

# Get environment variables
LIBRARY_NAME = get_env_variable('LIBRARY_NAME')
PLEX_URL = get_env_variable('PLEX_URL')
PLEX_TOKEN = get_env_variable('PLEX_TOKEN')

# Validate PLEX_URL
if not is_valid_url(PLEX_URL):
    app.logger.info("Error: PLEX_URL is not a valid URL.")
    sys.exit(1)

plex = PlexServer(PLEX_URL, PLEX_TOKEN)

def is_english_dubbed(data):
    audio_languages = data.get('episodeFile', {}).get('mediaInfo', {}).get('audioLanguages', [])
    is_dubbed = 'eng' in audio_languages
    app.logger.info(f"English dubbed: {is_dubbed}")
    return is_dubbed

def get_episode_from_data(data):
    show_title = data.get('series', {}).get('title')
    episode_title = data.get('episodes', [{}])[0].get('title')
    app.logger.info(f"Fetching episode: {episode_title} from show: {show_title}")
    show = plex.library.section(LIBRARY_NAME).get(show_title)
    episode = show.episode(episode_title)
    app.logger.info(f"Found episode: {episode.title}")
    return episode

def manage_collection(episode, collection_name='Latest Dubs'):
    app.logger.info(f"Managing collection for episode: {episode.title}")
    collection = None

    # Check if collection exists
    for col in plex.library.section(LIBRARY_NAME).collections():
        if col.title == collection_name:
            collection = col
            app.logger.info(f"Collection '{collection_name}' already exists.")
            break

    # Create collection and add episode if not found, else add episode if not present
    if collection is None:
        app.logger.info(f"Creating new collection '{collection_name}'.")
        collection = plex.library.section(LIBRARY_NAME).createCollection(title=collection_name, items=[episode])
    elif episode not in collection.items():
        app.logger.info(f"Adding episode '{episode.title}' to collection '{collection_name}'.")
        collection.addItems([episode])
    else:
        app.logger.info(f"Episode '{episode.title}' already in collection '{collection_name}'.")

    # Trimming the Collection
    if len(collection.items()) > 100:
        app.logger.info("Trimming the collection...")
        sorted_episodes = sorted(collection.items(), key=lambda ep: ep.originallyAvailableAt)
        episodes_to_remove = sorted_episodes[:-100]
        for ep in episodes_to_remove:
            app.logger.info(f"Removing episode '{ep.title}' from collection.")
        # Remove the episodes in bulk after logging
        collection.removeItems(episodes_to_remove)


@app.route('/webhook', methods=['POST'])
def webhook():
    app.logger.info("Received webhook")
    data = request.get_json()
    
    if data:
        event_type = data.get('eventType')
        # Handle deletion events
        if event_type == 'EpisodeFileDelete' and is_english_dubbed(data) and data.get('deleteReason') == 'upgrade':
            episode_id = data.get('episodes', [{}])[0].get('id')
            if episode_id:
                deleted_episodes.append((episode_id, time.time()))
                app.logger.info(f"Marked English dubbed episode {episode_id} as deleted due to upgrade.")

        # Handle download events
        elif event_type == 'Download':
            episode_id = data.get('episodes', [{}])[0].get('id')
            # Skip processing if recently deleted due to upgrade
            if any(ep_id == episode_id for ep_id, _ in deleted_episodes):
                app.logger.info(f"Skipping download of episode {episode_id} as it was a previous upgrade of an English dubbed episode.")
            elif is_english_dubbed(data):
                try:
                    episode = get_episode_from_data(data)
                    manage_collection(episode)
                except Exception as e:
                    app.logger.info(f"Error processing request: {e}")

    return "Webhook received", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
