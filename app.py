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

def get_closest_show(library_section, query_title, score_cutoff=75):
    shows = [show.title for show in library_section.all()]
    closest_match, score = process.extractOne(query_title, shows, score_cutoff=score_cutoff)
    
    if score >= score_cutoff:
        return library_section.get(closest_match)
    else:
        app.logger.info(f"No close match found for '{query_title}' with cutoff score of {score_cutoff}.")
        return None

def get_episode_from_data(LIBRARY_NAME, show_name, season_number, episode_number, max_retries=3, delay=10):
    app.logger.info(f"Verifying the show '{show_name}' is in Plex...")
    library_section = plex.library.section(LIBRARY_NAME)
    retries = 0
    show = None

    # Try to find the show
    while retries < max_retries and not show:
        try:
            show = library_section.get(show_name)
            app.logger.info(f"Found show: {show.title}")
        except NotFound:
            app.logger.info(f"Show '{show_name}' not found. Retrying...")
            time.sleep(delay)
        retries += 1

    # If show is not found, attempt fuzzy match
    if not show:
        app.logger.info(f"Attempting fuzzy match for show '{show_name}'.")
        show = get_closest_show(library_section, show_name)
        if not show:
            app.logger.error(f"Show '{show_name}' not found in library after retries and fuzzy match.")
            return None
        else:
            app.logger.info(f"Found show by fuzzy match: {show.title}")

    # Try to find the episode
    app.logger.info(f"Verifying the episode for '{show.title}' is in Plex...")
    retries = 0
    while retries < max_retries:
        try:
            episode = show.episode(season=season_number, episode=episode_number)
            app.logger.info(f"Found episode by season and number: {episode.title}")
            return episode
        except NotFound:
            app.logger.info(f"Episode not found. Retrying...")
            time.sleep(delay)
        except Exception as e:
            app.logger.error(f"Error fetching episode by season and number: {e}")
        retries += 1

    app.logger.error(f"Episode for Season {season_number}, Episode {episode_number} not found in '{show.title}' after retries.")
    return None

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

def sonarr_handle_download_event(LIBRARY_NAME, show_name, episode_id, season_number, episode_number):
    if any(ep_id == episode_id for ep_id, _ in deleted_episodes):
        app.logger.info("Skipping as it was a previous upgrade of an English dubbed episode.")
    else:
        try:
            episode = get_episode_from_data(LIBRARY_NAME, show_name, season_number, episode_number, max_retries=3, delay=10)
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

def sonarr_log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed, is_upgrade, air_date, season_number, episode_number):
    app.logger.info(" ")
    app.logger.info("Sonarr Webhook Received")
    app.logger.info(f"Event Type: {event_type}")
    app.logger.info(f"Show Title: {show_name}")
    app.logger.info(f"Episode: {episode_name} - ID: {episode_id}")
    app.logger.info(f"Season: {season_number}")
    app.logger.info(f"Episode: {episode_number}")
    app.logger.info(f"Air Date: {air_date}")
    app.logger.info(f"English Dubbed: {is_dubbed}")
    app.logger.info(f"Is Upgrade: {is_upgrade}")

@app.route('/sonarr', methods=['POST'])
def sonarr_webhook():
    data = request.get_json()
    event_type = data.get('eventType')
    show_name = data.get('series', {}).get('title')
    episode_name = data.get('episodes', [{}])[0].get('title')
    episode_id = data.get('episodes', [{}])[0].get('id')
    season_number = data.get('episodes', [{}])[0].get('seasonNumber')
    episode_number = data.get('episodes', [{}])[0].get('episodeNumber')
    air_date = data.get('episodes', [{}])[0].get('airDate')
    is_dubbed = is_english_dubbed(data)
    is_upgrade = data.get('isUpgrade', False)

    is_recent_release = is_recent_or_upcoming_release(air_date)

    sonarr_log_event_details(event_type, show_name, episode_name, episode_id, is_dubbed, is_upgrade, air_date, season_number, episode_number)

    if event_type == 'EpisodeFileDelete' and data.get('deleteReason') == 'upgrade' and is_dubbed:
        handle_deletion_event(episode_id)
    elif event_type == 'Download' and (is_upgrade or is_recent_release) and is_dubbed:
        if is_recent_release:
            sonarr_handle_download_event(SONARR_LIBRARY, show_name, episode_id, season_number, episode_number)

    return "Webhook received", 200

def get_closest_movie(library, query_title, score_cutoff=75):
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

def radarr_log_event_details(event_type, movie_title, movie_id, release_date, is_dubbed, is_upgrade):
    app.logger.info(" ")
    app.logger.info("Radarr Webhook Received")
    app.logger.info(f"Event Type: {event_type}")
    app.logger.info(f"Movie Title: {movie_title}")
    app.logger.info(f"Movie ID: {movie_id}")
    app.logger.info(f"Release Date: {release_date}")
    app.logger.info(f"English Dubbed: {is_dubbed}")
    app.logger.info(f"Is Upgrade: {is_upgrade}")

def is_recent_or_upcoming_release(date_str):
    if not date_str:
        return False
    release_or_air_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    current_date = datetime.datetime.utcnow().date()
    days_diff = (current_date - release_or_air_date).days
    return 0 <= days_diff <= 4 or release_or_air_date > current_date

@app.route('/radarr', methods=['POST'])
def radarr_webhook():
    data = request.get_json()
    event_type = data.get('eventType')
    movie_title = data.get('movie', {}).get('title')
    movie_id = data.get('movie', {}).get('id')
    is_dubbed = is_english_dubbed(data)
    is_upgrade = data.get('isUpgrade', False)
    release_date = data.get('movie', {}).get('releaseDate')
    is_recent_release = is_recent_or_upcoming_release(release_date)

    radarr_log_event_details(event_type, movie_title, movie_id, release_date, is_dubbed, is_upgrade)

    if event_type == 'MovieFileDelete' and data.get('deleteReason') == 'upgrade' and is_dubbed:
        handle_deletion_event(movie_id) 
    elif event_type == 'Download' and (is_upgrade or is_recent_release) and is_dubbed:
        radarr_handle_download_event(RADARR_LIBRARY, movie_title, movie_id)

    return "Webhook received", 200

