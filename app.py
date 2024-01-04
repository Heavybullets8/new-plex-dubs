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
SONARR_LIBRARY = get_env_variable('SONARR_LIBRARY')
RADARR_LIBRARY = get_env_variable('RADARR_LIBRARY')
PLEX_URL = get_env_variable('PLEX_URL')
PLEX_TOKEN = get_env_variable('PLEX_TOKEN')

# Validate PLEX_URL
if not is_valid_url(PLEX_URL):
    app.logger.info("Error: PLEX_URL is not a valid URL.")
    sys.exit(1)

plex = PlexServer(PLEX_URL, PLEX_TOKEN)

def is_english_dubbed(data):
    audio_languages = data.get('episodeFile', {}).get('mediaInfo', {}).get('audioLanguages', [])
    if not audio_languages:
        audio_languages = data.get('movieFile', {}).get('mediaInfo', {}).get('audioLanguages', [])
    is_dubbed_audio = 'eng' in audio_languages

    custom_formats = data.get('customFormatInfo', {}).get('customFormats', [])
    is_custom_format = any(cf.get('name') in ['Anime Dual Audio', 'Dubs Only'] for cf in custom_formats)

    return is_dubbed_audio or is_custom_format

def get_episode_from_data(LIBRARY_NAME, show_name, episode_name):
    app.logger.info(f"Ensuring show '{show_name}' exists in library.")
    try:
        show = plex.library.section(LIBRARY_NAME).get(show_name)
        episode = show.episode(episode_name)
        app.logger.info(f"Found episode: {episode.title}")
    except:
        app.logger.error(f"Episode '{episode_name}' in show '{show_name}' not found in library.")
        episode = None
    return episode

def manage_collection(LIBRARY_NAME, media, collection_name='Latest Dubs', is_movie=False):
    media_type = 'movie' if is_movie else 'episode'
    app.logger.info(f"Managing collection for {media_type}: {media.title}")
    collection = None

    # Check if collection exists
    for col in plex.library.section(LIBRARY_NAME).collections():
        if col.title == collection_name:
            collection = col
            app.logger.info(f"Collection '{collection_name}' already exists.")
            break

    # Create collection and add media if not found, else add media if not present
    if collection is None:
        app.logger.info(f"Creating new collection '{collection_name}'.")
        collection = plex.library.section(LIBRARY_NAME).createCollection(title=collection_name, items=[media])
    elif media not in collection.items():
        app.logger.info(f"Adding {media_type} '{media.title}' to collection '{collection_name}'.")
        collection.addItems([media])
    else:
        app.logger.info(f"{media_type.title()} '{media.title}' already in collection '{collection_name}'.")

    # Trimming the Collection
    if len(collection.items()) > 100:
        app.logger.info("Trimming the collection...")
        sorted_media = sorted(collection.items(), key=lambda m: m.originallyAvailableAt)
        media_to_remove = sorted_media[:-100]
        for m in media_to_remove:
            app.logger.info(f"Removing {media_type} '{m.title}' from collection.")
        # Remove the media items in bulk after logging
        collection.removeItems(media_to_remove)


def sonarr_handle_download_event(LIBRARY_NAME, show_name, episode_name, episode_id, is_dubbed):
    if any(ep_id == episode_id for ep_id, _ in deleted_episodes):
        app.logger.info("Skipping as it was a previous upgrade of an English dubbed episode.")
    elif is_dubbed:
        try:
            episode = get_episode_from_data(LIBRARY_NAME, show_name, episode_name)
            manage_collection(LIBRARY_NAME, episode)
        except Exception as e:
            app.logger.info(f"Error processing request: {e}")

def handle_deletion_event(media_id):
    if media_id:
        # Filter out the old entry of the media (movie or episode) if it exists
        temp = [(m_id, timestamp) for m_id, timestamp in deleted_episodes if m_id != media_id]
        deleted_episodes.clear()
        deleted_episodes.extend(temp)
        deleted_episodes.append((media_id, time.time()))
        app.logger.info("Updated deletion record due to upgrade.")

def sonarr_log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed):
    app.logger.info(" ")
    app.logger.info("Webhook Received")
    app.logger.info(f"Show Title: {show_name}")
    app.logger.info(f"Episode: {episode_name} - ID: {episode_id}")
    app.logger.info(f"Event Type: {event_type}")
    app.logger.info(f"English Dubbed: {is_dubbed}")

@app.route('/sonarr', methods=['POST'])
def sonarr_webhook():
    data = request.get_json()
    event_type = data.get('eventType')
    show_name = data.get('series', {}).get('title')
    episode_name = data.get('episodes', [{}])[0].get('title')
    episode_id = data.get('episodes', [{}])[0].get('id')
    is_dubbed = is_english_dubbed(data)

    sonarr_log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed)

    if event_type == 'EpisodeFileDelete' and data.get('deleteReason') == 'upgrade' and is_dubbed:
        handle_deletion_event(episode_id)
    elif event_type == 'Download':
        sonarr_handle_download_event(SONARR_LIBRARY, show_name, episode_name, episode_id, is_dubbed)

    return "Webhook received", 200

def get_movie_from_data(LIBRARY_NAME, movie_title):
    app.logger.info(f"Searching for movie '{movie_title}' in library.")
    try:
        movie = plex.library.section(LIBRARY_NAME).get(movie_title)
        app.logger.info(f"Found movie: {movie.title}")
    except:
        app.logger.error(f"Movie '{movie_title}' not found in library.")
        movie = None
    return movie

def radarr_handle_download_event(LIBRARY_NAME, movie_name, movie_id, is_dubbed):
    if any(m_id == movie_id for m_id, _ in deleted_episodes):
        app.logger.info("Skipping as it was a previous upgrade of an English dubbed movie.")
    elif is_dubbed:
        try:
            movie = get_movie_from_data(movie_name)
            manage_collection(LIBRARY_NAME, movie, is_movie=True)
        except Exception as e:
            app.logger.info(f"Error processing request: {e}")

def radarr_log_event_details(event_type, movie_title, movie_id, is_dubbed):
    app.logger.info(" ")
    app.logger.info("Radarr Webhook Received")
    app.logger.info(f"Movie Title: {movie_title}")
    app.logger.info(f"Movie ID: {movie_id}")
    app.logger.info(f"Event Type: {event_type}")
    app.logger.info(f"English Dubbed: {is_dubbed}")

@app.route('/radarr', methods=['POST'])
def radarr_webhook():
    data = request.get_json()
    event_type = data.get('eventType')
    movie_title = data.get('movie', {}).get('title')
    movie_id = data.get('movie', {}).get('id')
    is_dubbed = is_english_dubbed(data)

    radarr_log_event_details(event_type, movie_title, movie_id, is_dubbed)

    if event_type == 'MovieFileDelete' and data.get('deleteReason') == 'upgrade' and is_dubbed:
        handle_deletion_event(movie_id) 
    elif event_type == 'Download':
        radarr_handle_download_event(RADARR_LIBRARY, movie_title, movie_id, is_dubbed)

    return "Webhook received", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
