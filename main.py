"""
Vibe Coder Backend Orchestrator - v8.1 (Diagnostic Logging)

This version adds detailed exception logging to the main try/except block
to diagnose a silent 500 error.
"""

import os
import uuid
import traceback # NEW: Import the traceback library
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
PERSONALITY_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/personality"

# --- Helper Function for Personality ---
def get_personality_response(context, data=None):
    """Calls the personality agent to get a natural language response."""
    payload = {"data": {"context": context, "data": data}}
    response = requests.post(PERSONALITY_URL, json=payload)
    response.raise_for_status()
    return response.json().get("result", "I'm not sure how to respond.")

# ... (The /conversations and /conversation/<id> endpoints are unchanged)
@app.route("/conversations", methods=["GET"])
def get_conversations():
    conversations_ref = db.collection("conversations").order_by(
        "lastUpdated", direction=firestore.Query.DESCENDING
    ).limit(20)
    conversation_list = []
    for doc in conversations_ref.stream():
        convo_data = doc.to_dict()
        first_message = convo_data.get("messages", [{}])[0].get("content", "New Chat")
        conversation_list.append({"id": doc.id, "title": first_message})
    return jsonify(conversation_list)

@app.route("/conversation/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id):
    if not conversation_id: return jsonify({"error": "ID required."}), 400
    doc = db.collection("conversations").document(conversation_id).get()
    if not doc.exists: return jsonify({"error": "Not found."}), 404
    return jsonify(doc.to_dict())


@app.route("/chat", methods=["POST"])
def chat():
    """Manages the multi-turn conversation."""
    incoming_data = request.get_json()
    user_message = incoming_data["message"]
    conversation_id = incoming_data.get("conversation_id")

    # ... (State loading logic is unchanged)
    conversation_ref = None
    conversation = None
    if conversation_id:
        conversation_ref = db.collection("conversations").document(conversation_id)
        doc = conversation_ref.get()
        if doc.exists: conversation = doc.to_dict()
    
    if not conversation:
        conversation_id = str(uuid.uuid4())
        conversation = {"state": "new", "plan": None, "messages": []}
        conversation_ref = db.collection("conversations").document(conversation_id)

    conversation_state = conversation.get("state", "new")
    conversation["messages"].append({"role": "user", "content": user_message})

    try:
        # --- STATE MACHINE (logic is unchanged) ---
        if conversation_state == "awaiting_plan_approval":
            if user_message.lower() == "yes":
                plan = conversation.get("plan")
                if not plan or not plan.get("steps"): raise ValueError("No plan found.")
                
                first_step = plan["steps"][0]
                engineer_payload = {"data": first_step}
                code_response = requests.post(FRONTEND_ENGINEER_URL, json=engineer_payload)
                code_response.raise_for_status()
                code_file = code_response.json().get("result")
                
                conversation["state"] = "execution_complete"
                response_payload = {
                    "reply": get_personality_response("execution_complete", code_file),
                    "code_file": code_file,
                }
            else:
                response_payload = {"reply": get_personality_response("plan_rejected")}
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
                    "reply": get_personality_response("plan_generated", plan),
                }
            else:
                response_payload = {"reply": get_personality_response("triage_chitchat")}

        conversation["messages"].append({"role": "assistant", "content": response_payload})
        conversation["lastUpdated"] = firestore.SERVER_TIMESTAMP
        conversation_ref.set(conversation, merge=True)
        
        response_payload["conversation_id"] = conversation_id
        return jsonify(response_payload)

    except Exception as e:
        # --- ENHANCED LOGGING ---
        # This will print the full, detailed error to the logs.
        print(f"[Orchestrator] C_ID: {conversation_id} | A CRITICAL ERROR OCCURRED: {e}")
        traceback.print_exc()
        return jsonify({"error": "An internal error occurred. Check the server logs."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))