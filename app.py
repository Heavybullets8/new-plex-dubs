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

def get_episode_from_data(show_name, episode_name):
    app.logger.info(f"Ensuring show '{show_name}' exists in library.")
    show = plex.library.section(LIBRARY_NAME).get(show_name)
    episode = show.episode(episode_name)
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

def handle_download_event(show_name, episode_name, episode_id, is_dubbed):
    if any(ep_id == episode_id for ep_id, _ in deleted_episodes):
        app.logger.info("Skipping as it was a previous upgrade of an English dubbed episode.")
    elif is_dubbed:
        try:
            episode = get_episode_from_data(show_name, episode_name)
            manage_collection(episode)
        except Exception as e:
            app.logger.info(f"Error processing request: {e}")

def handle_deletion_event(episode_id):
    if episode_id:
        deleted_episodes[:] = [(ep_id, timestamp) for ep_id, timestamp in deleted_episodes if ep_id != episode_id]
        deleted_episodes.append((episode_id, time.time()))
        app.logger.info("Updated deletion record due to upgrade.")

def log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed):
    app.logger.info("\nWebhook Received")
    app.logger.info(f"Show Title: {show_name}")
    app.logger.info(f"Episode: {episode_name} - ID: {episode_id}")
    app.logger.info(f"Event Type: {event_type}")
    app.logger.info(f"Is English Dubbed: {is_dubbed}")

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    event_type = data.get('eventType')
    show_name = data.get('series', {}).get('title')
    episode_name = data.get('episodes', [{}])[0].get('title')
    episode_id = data.get('episodes', [{}])[0].get('id')
    is_dubbed = is_english_dubbed(data)

    log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed)

    if event_type == 'EpisodeFileDelete' and data.get('deleteReason') == 'upgrade' and is_dubbed:
        handle_deletion_event(data, episode_id, is_dubbed)
    elif event_type == 'Download':
        handle_download_event(show_name, episode_name, episode_id, is_dubbed)

    return "Webhook received", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
