# Plex Dubbed Episodes Updater Docker Container

## Overview
This Docker container updates your Plex server with the latest dubbed episodes that were upgraded. It handles webhooks from Sonarr and Radarr to manage a collection of the latest dubbed episodes and movies in your Plex library.

## Environment Variables

| Variable        | Description                           | Example Value      |
|-----------------|---------------------------------------|--------------------|
| `PORT`          | The port the container will listen on | `5000`             |
| `PLEX_URL`      | URL of your Plex server               | `http://plex:32400`|
| `PLEX_TOKEN`    | Your Plex server token                | `YourPlexToken`    |
| `SONARR_LIBRARY`| Sonarr library name in Plex           | `Anime Series`     |
| `RADARR_LIBRARY`| Radarr library name in Plex           | `Anime Movies`     |

## Usage
1. Set the environment variables in your Docker configuration.
2. Deploy the Docker container.
3. Configure Sonarr and Radarr to send webhooks to the container.

This container listens for webhooks from Sonarr and Radarr, and when it receives notification of an episode or movie upgrade, it checks if the media is dubbed. If dubbed, it updates the specified Plex collection with the latest media.

Additionally, I use tags for anime series, so any of my anime series will have the tag `anime` and only be sent to the webhook if it possesses that tag:

## Sonarr Settings

![image](https://github.com/Heavybullets8/new-plex-dubs/assets/20793231/1a2ca8d6-4d79-4188-b282-80c034af5479)

> `http://URL:PORT/sonarr`

## Radarr Settings 

![image](https://github.com/Heavybullets8/new-plex-dubs/assets/20793231/5003fdeb-7beb-4e3c-8fd1-d345b93876d5)

> `http://URL:PORT/radarr`

## Warning

I made this purely for personal use, but published it in the event anyone else found it useful. I likely will not offer any type of support. 

The Plex token is stored as an environment variable, which is unsafe, so use this at your own risk. 
