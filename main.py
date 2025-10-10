"""
Vibe Coder Backend Orchestrator - v3.0 (Stateful Agent)

This service acts as the central "Project Manager" agent. It now implements
a state machine to handle multi-turn conversations, enabling the "Confirm"
step of the core loop. It uses a simple in-memory dictionary for state
management as a "Proof of Tool" simplification.
"""

import os
import uuid
from flask import Flask, request, jsonify
import requests

# Create the web server application
app = Flask(__name__)

# --- In-Memory State Management (Proof of Tool Simplification) ---
# In a production system, this would be a real database (like Firestore).
conversations = {}

# --- AI Service Endpoints ---
TASK_CLASSIFIER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/taskClassifier"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"

@app.route("/chat", methods=["POST"])
def chat():
    """
    This endpoint now manages a multi-turn conversation using a state machine.
    """
    incoming_data = request.get_json()
    if not incoming_data or "message" not in incoming_data:
        return jsonify({"error": "Invalid request: 'message' key is required."}), 400

    user_message = incoming_data["message"]
    conversation_id = incoming_data.get("conversation_id")

    # If no conversation_id is provided, start a new conversation.
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        conversations[conversation_id] = {"state": "new", "plan": None}
        print(f"[Orchestrator] New conversation started: {conversation_id}")

    # Retrieve the current state of the conversation.
    conversation_state = conversations.get(conversation_id, {}).get("state", "new")
    print(f"[Orchestrator] C_ID: {conversation_id} | Current State: '{conversation_state}'")
    print(f"[Orchestrator] C_ID: {conversation_id} | User Message: '{user_message}'")

    try:
        # --- STATE MACHINE ---
        if conversation_state == "awaiting_plan_approval":
            # --- CONFIRM STEP ---
            if user_message.lower() == "yes":
                conversations[conversation_id]["state"] = "plan_approved"
                response_payload = {
                    "reply": "CONFIRMED: Plan approved. I will begin execution shortly.",
                    "conversation_id": conversation_id,
                }
            else:
                response_payload = {
                    "reply": "CONFIRMATION: Plan not approved. Please provide feedback or say 'yes' to approve.",
                    "conversation_id": conversation_id,
                }
        else:
            # --- TRIAGE & PLAN STEPS ---
            print(f"[Orchestrator] C_ID: {conversation_id} | Calling Task Classifier...")
            classifier_payload = {"data": user_message}
            response = requests.post(TASK_CLASSIFIER_URL, json=classifier_payload)
            response.raise_for_status()
            intent = response.json().get("result")
            print(f"[Orchestrator] C_ID: {conversation_id} | Received intent: '{intent}'")

            if intent == "task_request":
                print(f"[Orchestrator] C_ID: {conversation_id} | Calling Architect...")
                architect_payload = {"data": user_message}
                plan_response = requests.post(ARCHITECT_URL, json=architect_payload)
                plan_response.raise_for_status()
                plan = plan_response.json().get("result")
                
                # Save the plan and update the state
                conversations[conversation_id]["plan"] = plan
                conversations[conversation_id]["state"] = "awaiting_plan_approval"
                
                response_payload = {
                    "plan": plan,
                    "reply": "Here is the plan I have generated. Please review and respond with 'yes' to approve.",
                    "conversation_id": conversation_id,
                }
            else: # chitchat, clarification, or unknown
                response_payload = {
                    "reply": "TRIAGE: Intent recognized. How can I help with your main task?",
                    "conversation_id": conversation_id,
                }
        
        print(f"[Orchestrator] C_ID: {conversation_id} | Sending response payload.")
        return jsonify(response_payload)

    except requests.exceptions.RequestException as e:
        print(f"[Orchestrator] C_ID: {conversation_id} | Error during AI service call: {e}")
        return jsonify({"error": "Failed to communicate with the AI service."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))