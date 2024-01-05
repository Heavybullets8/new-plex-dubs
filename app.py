from flask import request
from src.config import app
from src.sonarr import sonarr_webhook
from src.radarr import radarr_webhook

@app.route('/sonarr', methods=['POST'])
def handle_sonarr():
    return sonarr_webhook(request)

@app.route('/radarr', methods=['POST'])
def handle_radarr():
    return radarr_webhook(request)