"""
Vibe Coder Backend Orchestrator - v4.1 (CORS Enabled)

This version implements a code-level CORS policy to allow the frontend
application to securely communicate with this backend service.
"""

import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS # Import the CORS library
import requests

# Create the web server application
app = Flask(__name__)

# --- CORS Configuration ---
# This is the critical step. We are telling the server to allow requests
# specifically from our deployed frontend's URL.
CORS(app, origins=["https://vibe-agent-phoenix.web.app"])

# --- In-Memory State Management ---
conversations = {}

# --- AI Service Endpoints ---
TASK_CLASSIFIER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/taskClassifier"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"
FRONTEND_ENGINEER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/frontendEngineer"

@app.route("/chat", methods=["POST"])
def chat():
    """
    This endpoint orchestrates the full Triage -> Plan -> Confirm -> Execute workflow.
    """
    # ... (The rest of the chat logic is unchanged)
    incoming_data = request.get_json()
    if not incoming_data or "message" not in incoming_data:
        return jsonify({"error": "Invalid request: 'message' key is required."}), 400

    user_message = incoming_data["message"]
    conversation_id = incoming_data.get("conversation_id")

    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        conversations[conversation_id] = {"state": "new", "plan": None}
        print(f"[Orchestrator] New conversation started: {conversation_id}")

    conversation = conversations.get(conversation_id, {})
    conversation_state = conversation.get("state", "new")
    print(f"[Orchestrator] C_ID: {conversation_id} | State: '{conversation_state}' | Message: '{user_message}'")

    try:
        if conversation_state == "awaiting_plan_approval":
            if user_message.lower() == "yes":
                print(f"[Orchestrator] C_ID: {conversation_id} | Plan approved. Beginning execution.")
                plan = conversation.get("plan")
                if not plan or not plan.get("steps"):
                    return jsonify({"error": "Cannot execute: No plan found."}), 500
                
                first_step = plan["steps"][0]
                print(f"[Orchestrator] C_ID: {conversation_id} | Executing step 1: '{first_step}'")
                
                engineer_payload = {"data": first_step}
                code_response = requests.post(FRONTEND_ENGINEER_URL, json=engineer_payload)
                code_response.raise_for_status()
                
                code_file = code_response.json().get("result")
                conversations[conversation_id]["state"] = "execution_complete"
                
                response_payload = {
                    "reply": f"EXECUTION: I have completed the first step: '{first_step}'. Here is the generated code.",
                    "code_file": code_file,
                    "conversation_id": conversation_id,
                }
            else:
                response_payload = {
                    "reply": "CONFIRMATION: Plan not approved. Please provide feedback.",
                    "conversation_id": conversation_id,
                }
        else:
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
                
                conversations[conversation_id]["plan"] = plan
                conversations[conversation_id]["state"] = "awaiting_plan_approval"
                
                response_payload = {
                    "plan": plan,
                    "reply": "Here is the plan. Please respond with 'yes' to approve.",
                    "conversation_id": conversation_id,
                }
            else:
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