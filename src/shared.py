from .config import app, plex, deleted_episodes, MAX_COLLECTION_SIZE, MAX_DATE_DIFF
import time, datetime

def is_english_dubbed(data):
    audio_languages = data.get('episodeFile', {}).get('mediaInfo', {}).get('audioLanguages', [])
    if not audio_languages:
        audio_languages = data.get('movieFile', {}).get('mediaInfo', {}).get('audioLanguages', [])
    is_dubbed_audio = 'eng' in audio_languages

    custom_formats = data.get('customFormatInfo', {}).get('customFormats', [])
    is_custom_format = any(cf.get('name') in ['Anime Dual Audio', 'Dubs Only'] for cf in custom_formats)

    return is_dubbed_audio or is_custom_format

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
    if len(collection.items()) > MAX_COLLECTION_SIZE:
        app.logger.info("Trimming and sorting the collection...")
        sorted_media = sorted(collection.items(), key=lambda m: m.originallyAvailableAt, reverse=True)
        media_to_remove = sorted_media[MAX_COLLECTION_SIZE:]
        for m in media_to_remove:
            app.logger.info(f"Removing {media_type} '{m.title}' from collection.")
        # Remove excess media items
        collection.removeItems(media_to_remove)

def handle_deletion_event(media_id):
    if media_id:
        # Filter out the old entry of the media (movie or episode) if it exists
        temp = [(m_id, timestamp) for m_id, timestamp in deleted_episodes if m_id != media_id]
        deleted_episodes.clear()
        deleted_episodes.extend(temp)
        deleted_episodes.append((media_id, time.time()))
        app.logger.info("Updated deletion record due to upgrade.")

def is_recent_or_upcoming_release(date_str):
    if not date_str:
        return False
    release_or_air_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    current_date = datetime.datetime.utcnow().date()
    days_diff = (current_date - release_or_air_date).days
    return 0 <= days_diff <= MAX_DATE_DIFF or release_or_air_date > current_date