# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install Flask and PlexAPI
RUN pip install Flask PlexAPI requests

# Copy the current directory contents into the container at /app
COPY . /app

# Define environment variable for the port and Plex credentials
ENV PORT 5000
ENV PLEX_URL=""
ENV PLEX_TOKEN=""

# Make port available to the world outside this container
EXPOSE $PORT

# Define environment variables
ENV NAME World
ENV PLEX_URL=""
ENV PLEX_TOKEN=""

# Run app.py when the container launches
CMD ["python", "app.py"]