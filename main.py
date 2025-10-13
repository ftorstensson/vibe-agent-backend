"""
Vibe Coder Backend Orchestrator - v7.0 (Chat History Loading)

This version adds a /conversation/<id> endpoint to retrieve the full message
history for a specific conversation, enabling the frontend to load and
resume past chats.
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
db = firestore.Client()

# --- AI Service Endpoints ---
TASK_CLASSIFIER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/taskClassifier"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"
FRONTEND_ENGINEER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/frontendEngineer"

# --- API Endpoints ---

@app.route("/conversations", methods=["GET"])
def get_conversations():
    """Retrieves a list of all conversations."""
    try:
        conversations_ref = db.collection("conversations").order_by(
            "lastUpdated", direction=firestore.Query.DESCENDING
        ).limit(20)
        
        conversation_list = []
        for doc in conversations_ref.stream():
            convo_data = doc.to_dict()
            first_message = convo_data.get("messages", [{}])[0].get("content", "New Chat")
            conversation_list.append({
                "id": doc.id,
                "title": first_message
            })
        return jsonify(conversation_list)
    except Exception as e:
        print(f"[Orchestrator] Error fetching conversations: {e}")
        return jsonify({"error": "Failed to fetch conversation history."}), 500

# --- NEW ENDPOINT TO GET A SINGLE CONVERSATION ---
@app.route("/conversation/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id):
    """Retrieves the full message history for a single conversation."""
    try:
        if not conversation_id:
            return jsonify({"error": "Conversation ID is required."}), 400
        
        conversation_ref = db.collection("conversations").document(conversation_id)
        conversation_doc = conversation_ref.get()
        
        if not conversation_doc.exists:
            return jsonify({"error": "Conversation not found."}), 404
            
        return jsonify(conversation_doc.to_dict())
    except Exception as e:
        print(f"[Orchestrator] Error fetching conversation {conversation_id}: {e}")
        return jsonify({"error": "Failed to fetch conversation."}), 500

@app.route("/chat", methods=["POST"])
def chat():
    """Manages the multi-turn conversation."""
    # ... (The rest of the chat logic is unchanged)
    incoming_data = request.get_json()
    if not incoming_data or "message" not in incoming_data:
        return jsonify({"error": "Invalid request: 'message' key is required."}), 400

    user_message = incoming_data["message"]
    conversation_id = incoming_data.get("conversation_id")

    conversation_ref = None
    conversation = None
    if conversation_id:
        conversation_ref = db.collection("conversations").document(conversation_id)
        conversation_doc = conversation_ref.get()
        if conversation_doc.exists:
            conversation = conversation_doc.to_dict()
    
    if not conversation:
        conversation_id = str(uuid.uuid4())
        conversation = {"state": "new", "plan": None, "messages": []}
        conversation_ref = db.collection("conversations").document(conversation_id)

    conversation_state = conversation.get("state", "new")
    conversation["messages"].append({"role": "user", "content": user_message})

    try:
        if conversation_state == "awaiting_plan_approval":
            if user_message.lower() == "yes":
                plan = conversation.get("plan")
                if not plan or not plan.get("steps"):
                    raise ValueError("Cannot execute: No plan found.")
                
                first_step = plan["steps"][0]
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
            classifier_payload = {"data": user_message}
            response = requests.post(TASK_CLASSIFIER_URL, json=classifier_payload)
            response.raise_for_status()
            intent = response.json().get("result")

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

        conversation["messages"].append({"role": "assistant", "content": response_payload})
        conversation["lastUpdated"] = firestore.SERVER_TIMESTAMP
        conversation_ref.set(conversation, merge=True)
        
        response_payload["conversation_id"] = conversation_id
        return jsonify(response_payload)

    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"[Orchestrator] C_ID: {conversation_id} | ERROR: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))