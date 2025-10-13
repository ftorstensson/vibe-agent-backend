"""
Vibe Coder Backend Orchestrator - v5.0 (Persistent Memory Agent)

This version refactors the agent's state management from an in-memory
dictionary to a persistent Firestore database. This gives the agent a
permanent memory, allowing conversations to survive server restarts and
deployments.
"""

import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from google.cloud import firestore

# --- Initialization ---
app = Flask(__name__)
CORS(app, origins=["https://vibe-agent-phoenix.web.app"])

# Initialize the Firestore client. It will automatically use the
# credentials and project ID from the Cloud Run environment.
db = firestore.Client()

# --- AI Service Endpoints ---
TASK_CLASSIFIER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/taskClassifier"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"
FRONTEND_ENGINEER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/frontendEngineer"

@app.route("/chat", methods=["POST"])
def chat():
    """
    This endpoint manages the multi-turn conversation, now with
    persistent memory provided by Firestore.
    """
    incoming_data = request.get_json()
    if not incoming_data or "message" not in incoming_data:
        return jsonify({"error": "Invalid request: 'message' key is required."}), 400

    user_message = incoming_data["message"]
    conversation_id = incoming_data.get("conversation_id")

    # --- State Loading ---
    conversation_ref = None
    if conversation_id:
        conversation_ref = db.collection("conversations").document(conversation_id)
        conversation_doc = conversation_ref.get()
        if conversation_doc.exists:
            conversation = conversation_doc.to_dict()
        else: # Handle case where a bad ID is sent
            conversation_id = None
    
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        conversation = {"state": "new", "plan": None, "messages": []}
        conversation_ref = db.collection("conversations").document(conversation_id)
        print(f"[Orchestrator] New conversation started: {conversation_id}")

    conversation_state = conversation.get("state", "new")
    print(f"[Orchestrator] C_ID: {conversation_id} | State: '{conversation_state}' | Message: '{user_message}'")

    # Add the new user message to the conversation history
    conversation["messages"].append({"role": "user", "content": user_message})

    try:
        # --- STATE MACHINE ---
        if conversation_state == "awaiting_plan_approval":
            if user_message.lower() == "yes":
                print(f"[Orchestrator] C_ID: {conversation_id} | Plan approved. Executing.")
                plan = conversation.get("plan")
                if not plan or not plan.get("steps"):
                    raise ValueError("Cannot execute: No plan found in conversation.")
                
                first_step = plan["steps"][0]
                print(f"[Orchestrator] C_ID: {conversation_id} | Executing step 1: '{first_step}'")
                
                engineer_payload = {"data": first_step}
                code_response = requests.post(FRONTEND_ENGINEER_URL, json=engineer_payload)
                code_response.raise_for_status()
                code_file = code_response.json().get("result")
                
                conversation["state"] = "execution_complete"
                response_payload = {
                    "reply": f"EXECUTION: Step 1 complete: '{first_step}'. Here is the code.",
                    "code_file": code_file,
                }
            else:
                response_payload = {"reply": "CONFIRMATION: Plan not approved."}
        else:
            # --- TRIAGE & PLAN STEPS ---
            classifier_payload = {"data": user_message}
            response = requests.post(TASK_CLASSIFIER_URL, json=classifier_payload)
            response.raise_for_status()
            intent = response.json().get("result")
            print(f"[Orchestrator] C_ID: {conversation_id} | Intent: '{intent}'")

            if intent == "task_request":
                architect_payload = {"data": user_message}
                plan_response = requests.post(ARCHITECT_URL, json=architect_payload)
                plan_response.raise_for_status()
                plan = plan_response.json().get("result")
                
                conversation["plan"] = plan
                conversation["state"] = "awaiting_plan_approval"
                response_payload = {
                    "plan": plan,
                    "reply": "Here is the plan. Please respond with 'yes' to approve.",
                }
            else:
                response_payload = {"reply": "TRIAGE: Intent recognized."}

        # --- State Saving ---
        conversation["messages"].append({"role": "assistant", "content": response_payload})
        conversation_ref.set(conversation)
        
        # Add conversation_id to the final response to the user
        response_payload["conversation_id"] = conversation_id
        return jsonify(response_payload)

    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"[Orchestrator] C_ID: {conversation_id} | ERROR: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))