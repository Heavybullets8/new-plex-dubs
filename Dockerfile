# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install Flask, PlexAPI, fuzzywuzzy, python-Levenshtein, and Gunicorn
RUN pip install Flask PlexAPI fuzzywuzzy python-Levenshtein gunicorn

# Copy the current directory contents into the container at /app
COPY . /app

# Define environment variable for the port and Plex credentials
ENV PORT 5000
ENV PLEX_URL=""
ENV PLEX_TOKEN=""
ENV SONARR_LIBRARY=""
ENV RADARR_LIBRARY=""

# Make port available to the world outside this container
EXPOSE $PORT

# Run app.py using Gunicorn when the container launches
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:${PORT}", "app:app"]
