from .config import app, plex, deleted_episodes, RADARR_LIBRARY
from .shared import is_english_dubbed, manage_collection, is_recent_or_upcoming_release, handle_deletion_event
from plexapi.exceptions import NotFound
from fuzzywuzzy import process

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

@app.route('/radarr', methods=['POST'])
def radarr_webhook(request):
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