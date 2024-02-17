from .config import app, plex, MAX_COLLECTION_SIZE, MAX_DATE_DIFF
import datetime, fcntl

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
    else:
        app.logger.info(f"{media_type} '{media.title}' already in collection.")

    # Check if the collection size exceeds the maximum allowed
    if len(collection.items()) > MAX_COLLECTION_SIZE:
        app.logger.info("Trimming the collection to the maximum allowed size...")
        
        items = collection.items()
        num_items_to_remove = len(items) - MAX_COLLECTION_SIZE
        # Select items to be removed based on the collection exceeding the MAX_COLLECTION_SIZE
        items_to_remove = items[-num_items_to_remove:]
        
        # Log the titles of the items that are to be removed
        for item in items_to_remove:
            app.logger.info(f"Removing item: '{item.title}' from the collection.")
        
        # Remove the identified items from the collection
        collection.removeItems(items_to_remove)


def trim_file(file_path, max_entries):
    with open(file_path, "r+") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        lines = file.readlines()
        if len(lines) > max_entries:
            file.seek(0)
            file.truncate()
            file.writelines(lines[-max_entries:])  # Keep only the last max_entries
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)

def handle_deletion_event(media_id):
    with open("/tmp/deleted_media_ids.txt", "a+") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        file.seek(0)  # Go to the beginning of the file
        if str(media_id) not in file.read():
            file.write(f"{media_id}\n")
            app.logger.info(f"Added {media_id} to deletion record.")
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    
    trim_file("/tmp/deleted_media_ids.txt", 100)  # Limit to 100 entries


def is_recent_or_upcoming_release(date_str):
    if not date_str:
        return False
    release_or_air_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    current_date = datetime.datetime.utcnow().date()
    days_diff = (current_date - release_or_air_date).days
    return 0 <= days_diff <= MAX_DATE_DIFF or release_or_air_date > current_date

def was_media_deleted(media_id):
    with open("/tmp/deleted_media_ids.txt", "r") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_SH)
        deleted_ids = file.read().splitlines()
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    
    return str(media_id) in deleted_ids

