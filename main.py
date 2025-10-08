import os
from flask import Flask, request, jsonify
import requests

# Create the web server application
app = Flask(__name__)

# Define the single endpoint for our service, which only accepts POST requests
@app.route("/chat", methods=["POST"])
def chat():
    """
    This endpoint acts as the orchestrator. It receives a request from the
    frontend, calls the Genkit AI service, and returns the response.
    """
    
    # This is the URL of the 'hello' Firebase Function we successfully deployed.
    genkit_function_url = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/hello"
    
    # For this first version, we will ignore any input from the user and
    # send a hardcoded payload to our Genkit function.
    # The format {"data": {...}} is required by the onCallGenkit trigger.
    payload_to_send = {"data": {"name": "Backend Orchestrator"}}
    
    try:
        # Use the 'requests' library to make a POST request to our Genkit function
        response = requests.post(genkit_function_url, json=payload_to_send)
        
        # This line will raise an error if the function returned a bad status (like 404 or 500)
        response.raise_for_status()
        
        # Return the JSON response from the Genkit function back to the original caller
        return jsonify(response.json())
        
    except requests.exceptions.RequestException as e:
        # If anything goes wrong with the network request, log the error
        # and return a generic error message.
        print(f"Error calling Genkit function: {e}")
        return jsonify({"error": "Failed to communicate with the AI service."}), 500

# This block allows the Flask server to be started correctly by Google Cloud Run
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))