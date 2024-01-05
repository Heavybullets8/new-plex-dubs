# Plex Dubbed Episodes Updater Docker Container

## Overview

Receives webhooks from Sonarr and Radarr, and updates a Plex collection with the latest dubbed episodes/movies.

## Environment Variables

| Variable             | Required/Default                 | Description                                           | Example Value      |
|----------------------|----------------------------------|-------------------------------------------------------|--------------------|
| `PORT`               | Not required, default `5000`     | The port the container will listen on                 | `5000`             |
| `PLEX_URL`           | **Required**, no default         | URL of your Plex server                               | `http://plex:32400`|
| `PLEX_TOKEN`         | **Required**, no default         | Your Plex server token                                | `YourPlexToken`    |
| `PLEX_ANIME_SERIES`  | **Required**, no default         | Plex library name for anime series (Sonarr)           | `Anime Series`     |
| `PLEX_ANIME_MOVIES`  | **Required**, no default         | Plex library name for anime movies (Radarr)           | `Anime Movies`     |
| `MAX_COLLECTION_SIZE`| Not required, default `100`      | Max number of episodes/movies in the collection       | `100`              |
| `MAX_DATE_DIFF`      | Not required, default `4`        | Max days difference for considering recent releases   | `4`                |

## Usage

1. Set the environment variables in your Docker configuration.
2. Deploy the Docker container.
3. Configure Sonarr and Radarr to send webhooks to the container.

This container listens for webhooks from Sonarr and Radarr, and when it receives notification of an episode or movie upgrade, it checks if the media is dubbed. If dubbed, it updates the specified Plex collection with the latest media.

Additionally, I use tags for anime series, so any of my anime series will have the tag `anime` and only be sent to the webhook if it possesses that tag:

## Sonarr Settings

![image](https://github.com/Heavybullets8/new-plex-dubs/assets/20793231/3847d1ca-e902-4567-9877-63a835aeb31a)

> `http://URL:PORT/sonarr`

## Radarr Settings 

![image](https://github.com/Heavybullets8/new-plex-dubs/assets/20793231/11aa2328-438b-47bd-bafd-4a634d373f64)

> `http://URL:PORT/radarr`

## Warning

I made this purely for personal use, but published it in the event anyone else found it useful. I likely will not offer any type of support. 

The Plex token is stored as an environment variable, which is unsafe, so use this at your own risk. 
