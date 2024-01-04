from flask import Flask, request
from plexapi.server import PlexServer, NotFound
from urllib.parse import urlparse
from fuzzywuzzy import process
from collections import deque
import os, sys, time, datetime

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

def get_closest_episode(show, query_title, score_cutoff=90):
    episodes = [ep.title for ep in show.episodes()]
    closest_match = process.extractOne(query_title, episodes, score_cutoff=score_cutoff)
    
    if closest_match and closest_match[1] >= score_cutoff:
        return show.episode(closest_match[0])
    else:
        app.logger.info(f"No close match found for episode '{query_title}' in show '{show.title}' with cutoff score of {score_cutoff}.")
        return None

def get_closest_show(library_section, query_title, score_cutoff=90):
    shows = [show.title for show in library_section.all()]
    closest_match, score = process.extractOne(query_title, shows, score_cutoff=score_cutoff)
    
    if score >= score_cutoff:
        return library_section.get(closest_match)
    else:
        app.logger.info(f"No close match found for '{query_title}' with cutoff score of {score_cutoff}.")
        return None

def get_episode_from_data(LIBRARY_NAME, show_name, episode_name):
    app.logger.info(f"Attempting to locate show '{show_name}' in library.")
    library_section = plex.library.section(LIBRARY_NAME)
    try:
        show = library_section.get(show_name)
    except NotFound:
        app.logger.info("Exact match not found, attempting fuzzy match for show.")
        show = get_closest_show(library_section, show_name)

    if show:
        try:
            episode = show.episode(episode_name)
        except NotFound:
            app.logger.info("Exact match not found, attempting fuzzy match for episode.")
            episode = get_closest_episode(show, episode_name)
        except Exception as e:
            app.logger.error(f"Error fetching episode: {e}")
            episode = None
    else:
        app.logger.error(f"Show '{show_name}' not found in library.")
        episode = None

    if episode:
        app.logger.info(f"Found episode: {episode.title}")
    return episode

def manage_collection(LIBRARY_NAME, media, collection_name='Latest Dubs', is_movie=False):
    media_type = 'movie' if is_movie else 'episode'
    app.logger.info(f"Managing and sorting collection for {media_type}: {media.title}")
    collection = None

    # Check if collection exists and retrieve it
    for col in plex.library.section(LIBRARY_NAME).collections():
        if col.title == collection_name:
            collection = col
            app.logger.info(f"Collection '{collection_name}' exists.")
            break

    # Create collection if it doesn't exist
    if collection is None:
        app.logger.info(f"Creating new collection '{collection_name}'.")
        collection = plex.library.section(LIBRARY_NAME).createCollection(title=collection_name, items=[media])
        # Set collection sort
        collection.sortUpdate(sort="custom")
        return

    # Add media to collection if not present
    if media not in collection.items():
        app.logger.info(f"Adding {media_type} '{media.title}' to collection '{collection_name}'.")
        collection.addItems([media])
        # Move the media to the front of the collection
        collection.moveItem(media, after=None)
        app.logger.info(f"Moved {media_type} '{media.title}' to the front of collection.")

    # Trimming and sorting the collection
    if len(collection.items()) > 100:
        app.logger.info("Trimming and sorting the collection...")
        sorted_media = sorted(collection.items(), key=lambda m: m.originallyAvailableAt, reverse=True)
        media_to_remove = sorted_media[100:]
        for m in media_to_remove:
            app.logger.info(f"Removing {media_type} '{m.title}' from collection.")
        # Remove excess media items
        collection.removeItems(media_to_remove)

def sonarr_handle_download_event(LIBRARY_NAME, show_name, episode_name, episode_id):
    if any(ep_id == episode_id for ep_id, _ in deleted_episodes):
        app.logger.info("Skipping as it was a previous upgrade of an English dubbed episode.")
    else:
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

def sonarr_log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed, is_upgrade):
    app.logger.info(" ")
    app.logger.info("Sonarr Webhook Received")
    app.logger.info(f"Show Title: {show_name}")
    app.logger.info(f"Episode: {episode_name} - ID: {episode_id}")
    app.logger.info(f"Event Type: {event_type}")
    app.logger.info(f"English Dubbed: {is_dubbed}")
    app.logger.info(f"Is Upgrade: {is_upgrade}")

def is_recent_or_upcoming_release(air_date_utc):
    if not air_date_utc:
        return False
    air_date = datetime.datetime.fromisoformat(air_date_utc[:-1])
    current_date = datetime.datetime.utcnow()
    days_diff = (current_date - air_date).days
    return days_diff <= 3 or air_date > current_date

@app.route('/sonarr', methods=['POST'])
def sonarr_webhook():
    data = request.get_json()
    event_type = data.get('eventType')
    show_name = data.get('series', {}).get('title')
    episode_name = data.get('episodes', [{}])[0].get('title')
    episode_id = data.get('episodes', [{}])[0].get('id')
    air_date_utc = data.get('episodes', [{}])[0].get('airDateUtc')
    is_dubbed = is_english_dubbed(data)
    is_upgrade = data.get('isUpgrade', False)

    is_recent_release = is_recent_or_upcoming_release(air_date_utc)

    sonarr_log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed, is_upgrade, air_date_utc)

    if event_type == 'EpisodeFileDelete' and data.get('deleteReason') == 'upgrade' and is_dubbed:
        handle_deletion_event(episode_id)
    elif event_type == 'Download' and (is_upgrade or is_recent_release) and is_dubbed:
        sonarr_handle_download_event(SONARR_LIBRARY, show_name, episode_name, episode_id)

    return "Webhook received", 200

def get_closest_movie(library, query_title, score_cutoff=90):
    movies = [movie.title for movie in library.all()]
    closest_match = process.extractOne(query_title, movies, score_cutoff=score_cutoff)
    
    if closest_match and closest_match[1] >= score_cutoff:
        return library.get(closest_match[0])
    else:
        app.logger.info(f"No close match found for movie '{query_title}' with cutoff score of {score_cutoff}.")
        return None

def get_movie_from_data(LIBRARY_NAME, movie_title):
    app.logger.info(f"Searching for movie '{movie_title}' in library.")
    try:
        library = plex.library.section(LIBRARY_NAME)
        movie = get_closest_movie(library, movie_title)
        app.logger.info(f"Found movie: {movie.title}")
    except NotFound:
        app.logger.error(f"Movie '{movie_title}' not found in library.")
        movie = None
    except Exception as e:
        app.logger.error(f"Error searching for movie: {e}")
        movie = None
    return movie

def radarr_handle_download_event(LIBRARY_NAME, movie_name, movie_id):
    if any(m_id == movie_id for m_id, _ in deleted_episodes):
        app.logger.info("Skipping as it was a previous upgrade of an English dubbed movie.")
    else:
        try:
            movie = get_movie_from_data(movie_name)
            manage_collection(LIBRARY_NAME, movie, is_movie=True)
        except Exception as e:
            app.logger.info(f"Error processing request: {e}")

def radarr_log_event_details(event_type, movie_title, movie_id, is_dubbed, is_upgrade):
    app.logger.info(" ")
    app.logger.info("Radarr Webhook Received")
    app.logger.info(f"Movie Title: {movie_title}")
    app.logger.info(f"Movie ID: {movie_id}")
    app.logger.info(f"Event Type: {event_type}")
    app.logger.info(f"English Dubbed: {is_dubbed}")
    app.logger.info(f"Is Upgrade: {is_upgrade}")

def is_recent_or_upcoming_release_movie(release_date_str):
    if not release_date_str:
        return False
    release_date = datetime.datetime.strptime(release_date_str, '%Y-%m-%d').date()
    current_date = datetime.datetime.utcnow().date()
    days_diff = (current_date - release_date).days
    return days_diff <= 3 or release_date > current_date

@app.route('/radarr', methods=['POST'])
def radarr_webhook():
    data = request.get_json()
    event_type = data.get('eventType')
    movie_title = data.get('movie', {}).get('title')
    movie_id = data.get('movie', {}).get('id')
    is_dubbed = is_english_dubbed(data)
    is_upgrade = data.get('isUpgrade', False)
    release_date_str = data.get('movie', {}).get('releaseDate')
    is_recent_release = is_recent_or_upcoming_release_movie(release_date_str)


    radarr_log_event_details(event_type, movie_title, movie_id, is_dubbed, is_upgrade)

    if event_type == 'MovieFileDelete' and data.get('deleteReason') == 'upgrade' and is_dubbed:
        handle_deletion_event(movie_id) 
    elif event_type == 'Download' and (is_upgrade or is_recent_release) and is_dubbed:
        radarr_handle_download_event(RADARR_LIBRARY, movie_title, movie_id)

    return "Webhook received", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
