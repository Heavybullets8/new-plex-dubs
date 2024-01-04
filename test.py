import datetime

# Function to check if a Sonarr episode release date is recent or upcoming
def is_recent_or_upcoming_release_sonarr(air_date_utc):
    if not air_date_utc:
        return False
    air_date = datetime.datetime.fromisoformat(air_date_utc[:-1])
    current_date = datetime.datetime.utcnow()
    days_diff = (current_date - air_date).days
    return days_diff <= 3 or air_date > current_date

# Function to check if a Radarr movie release date is recent or upcoming
def is_recent_or_upcoming_release_radarr(release_date_str):
    if not release_date_str:
        return False
    release_date = datetime.datetime.strptime(release_date_str, '%Y-%m-%d').date()
    current_date = datetime.datetime.utcnow().date()
    days_diff = (current_date - release_date).days
    return days_diff <= 3 or release_date > current_date

# Test inputs for Sonarr
sonarr_test_inputs = ["2023-10-21T13:00:00Z", "2024-01-21T13:00:00Z", "2023-10-03T13:00:00Z"]

# Test inputs for Radarr
radarr_test_inputs = ["2020-11-23", "2024-11-23", "2024-01-04"]

# Testing Sonarr function
sonarr_results = {input_date: is_recent_or_upcoming_release_sonarr(input_date) for input_date in sonarr_test_inputs}

# Testing Radarr function
radarr_results = {input_date: is_recent_or_upcoming_release_radarr(input_date) for input_date in radarr_test_inputs}

print(sonarr_results, radarr_results)

