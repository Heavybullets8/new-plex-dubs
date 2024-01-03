from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Webhook received:", data)
    return jsonify({"message": "Received"}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
