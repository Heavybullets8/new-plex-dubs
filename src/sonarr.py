from .config import app, plex, deleted_episodes, SONARR_LIBRARY
from .shared import is_english_dubbed, manage_collection, handle_deletion_event, is_recent_or_upcoming_release
import time
from fuzzywuzzy import process
from plexapi.exceptions import NotFound

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

def sonarr_handle_download_event(LIBRARY_NAME, show_name, episode_id, season_number, episode_number):
    if any(ep_id == episode_id for ep_id, _ in deleted_episodes):
        app.logger.info("Skipping as it was a previous upgrade of an English dubbed episode.")
    else:
        try:
            episode = get_episode_from_data(LIBRARY_NAME, show_name, season_number, episode_number, max_retries=3, delay=10)
            manage_collection(LIBRARY_NAME, episode)
        except Exception as e:
            app.logger.info(f"Error processing request: {e}")

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

def sonarr_webhook(request):
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