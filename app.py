from flask import Flask, request
from plexapi.server import PlexServer
from urllib.parse import urlparse
import os, sys

def get_env_variable(var_name, required=True):
    value = os.getenv(var_name)
    if required and not value:
        print(f"Error: The {var_name} environment variable is required.")
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
    print("Error: PLEX_URL is not a valid URL.")
    sys.exit(1)

plex = PlexServer(PLEX_URL, PLEX_TOKEN)

app = Flask(__name__)

def is_english_dubbed(data):
    audio_languages = data.get('episodeFile', {}).get('mediaInfo', {}).get('audioLanguages', [])
    return 'eng' in audio_languages

def get_episode_from_data(data):
    show_title = data.get('series', {}).get('title')
    episode_title = data.get('episodes', [{}])[0].get('title')
    show = plex.library.section(LIBRARY_NAME).get(show_title)
    return show.episode(episode_title)

def manage_collection(episode, collection_name='Latest Dubs'):
    collection = None

    # Check if collection exists
    for col in plex.library.section(LIBRARY_NAME).collections():
        if col.title == collection_name:
            collection = col
            break

    # If collection does not exist, create it and add the episode
    if collection is None:
        collection = plex.library.section(LIBRARY_NAME).createCollection(title=collection_name, items=[episode])
    else:
        # Check if the episode is already in the collection
        if episode not in collection.items():
            collection.add(episode)

    # Trimming the Collection
    if len(collection.items()) > 100:
        sorted_episodes = sorted(collection.items(), key=lambda ep: ep.originallyAvailableAt)
        episodes_to_remove = sorted_episodes[:-100]
        for ep in episodes_to_remove:
            ep.removeCollection(collection_name)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and is_english_dubbed(data):
        try:
            episode = get_episode_from_data(data)
            manage_collection(episode)
        except Exception as e:
            print(f"Error processing request: {e}")
    return "Webhook received", 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)