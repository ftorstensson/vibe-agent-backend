"""
Vibe Coder Backend Orchestrator - v1.0 (Triage Agent)

This service acts as the central "Project Manager" agent for the Vibe Coder
Agency. It exposes a single /chat endpoint that implements the "Triage" step
of the core conversational loop by calling the taskClassifierFlow in the
Genkit AI Services Engine.
"""

import os
from flask import Flask, request, jsonify
import requests

# Create the web server application
app = Flask(__name__)

# This is the URL of our 'taskClassifier' Genkit function.
GENKIT_FUNCTION_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/taskClassifier"

# Define the single endpoint for our service
@app.route("/chat", methods=["POST"])
def chat():
    """
    This endpoint implements the TRIAGE step of the Project Manager's core loop.
    It receives a user's message, classifies its intent, and returns a
    context-aware response.
    """

    # 1. Get the user's message from the incoming request body.
    # We expect a JSON payload like: {"message": "your message here"}
    incoming_data = request.get_json()
    if not incoming_data or "message" not in incoming_data:
        return jsonify({"error": "Invalid request: 'message' key is required."}), 400

    user_message = incoming_data["message"]
    print(f"[Orchestrator] Received user message: '{user_message}'")

    # 2. Prepare the payload to call the Genkit classifier function.
    # The onCall trigger expects the format {"data": ...}
    payload_to_send = {"data": user_message}

    try:
        # 3. Call the AI Service to classify the intent.
        print(f"[Orchestrator] Calling Task Classifier...")
        response = requests.post(GENKIT_FUNCTION_URL, json=payload_to_send)
        response.raise_for_status()  # Check for HTTP errors

        classification_result = response.json()
        intent = classification_result.get("result")
        print(f"[Orchestrator] Received intent: '{intent}'")

        # 4. TRIAGE: Decide what to do based on the classified intent.
        if intent == "task_request":
            response_message = "TRIAGE: Intent recognized as 'task_request'. Acknowledged. I will begin planning soon."
        elif intent == "chitchat":
            response_message = "TRIAGE: Intent recognized as 'chitchat'. Hello to you too!"
        elif intent == "clarification":
            response_message = "TRIAGE: Intent recognized as 'clarification'. I will provide more details shortly."
        else:
            # This is a fallback for safety, in case the AI returns an unexpected value.
            response_message = "TRIAGE: Could not determine intent. Awaiting further instruction."

        print(f"[Orchestrator] Sending response: '{response_message}'")
        return jsonify({"reply": response_message})

    except requests.exceptions.RequestException as e:
        print(f"[Orchestrator] Error calling Genkit function: {e}")
        return jsonify({"error": "Failed to communicate with the AI service."}), 500

# This block allows the Flask server to be started correctly by Google Cloud Run
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))