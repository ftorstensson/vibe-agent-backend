"""
Vibe Coder Backend Orchestrator - v14.0 (Real-Time UX)

This version implements the "Real-Time UX" mission by refactoring the /chat
endpoint to be fully asynchronous, following the "Placeholder" protocol.
It now immediately creates a placeholder message in Firestore and runs the
AI workflow in a background thread.
"""

import os
import uuid
import traceback
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from flasgger import Swagger

# --- Initialization ---
app = Flask(__name__)
CORS(app, origins=["https://vibe-agent-phoenix.web.app"])
swagger = Swagger(app)

# Initialize Firebase Admin SDK
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {'projectId': 'vibe-agent-final'})
db = firestore.client()

# --- AI Service Endpoints ---
PROJECT_MANAGER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/projectManager"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"

def run_ai_workflow(conversation_id, messages_ref, placeholder_ref):
    """
    This function runs the entire AI workflow in a background thread.
    """
    try:
        conversation_doc = db.collection("conversations").document(conversation_id).get()
        conversation = conversation_doc.to_dict()
        
        print(f"[Executor BG] C_ID: {conversation_id} | Calling PM Brain...")
        pm_payload = {"data": conversation.get("messages", [])}
        pm_response = requests.post(PROJECT_MANAGER_URL, json=pm_payload)
        pm_response.raise_for_status()
        decision = pm_response.json().get("result")
        print(f"[Executor BG] C_ID: {conversation_id} | Brain's decision: {decision}")

        action = decision.get("action")
        final_payload = {}
        
        # NOTE: State machine logic is temporarily removed for this refactor
        # and will be re-introduced in the new real-time architecture.

        if action == "call_architect":
            print(f"[Executor BG] C_ID: {conversation_id} | Executing: Call Architect...")
            architect_payload = {"data": decision.get("task")}
            plan_response = requests.post(ARCHITECT_URL, json=architect_payload)
            plan_response.raise_for_status()
            plan = plan_response.json().get("result")

            intermediate_message_ref = messages_ref.add({
                "role": "assistant",
                "content": {"reply": decision.get("text"), "plan": plan},
                "timestamp": firestore.SERVER_TIMESTAMP
            })

            print(f"[Executor BG] C_ID: {conversation_id} | Plan received. Calling brain for presentation...")
            current_messages_snapshot = messages_ref.order_by("timestamp").get()
            current_messages = [msg.to_dict() for msg in current_messages_snapshot]
            
            pm_payload_2 = {"data": current_messages}
            pm_response_2 = requests.post(PROJECT_MANAGER_URL, json=pm_payload_2)
            pm_response_2.raise_for_status()
            final_decision = pm_response_2.json().get("result")
            
            final_payload = {"reply": final_decision.get("text"), "plan": plan, "invoked_agent": "architect"}
        
        elif action == "reply_to_user":
            final_payload = {"reply": decision.get("text")}
            
        else: # Handle call_engineer and other future actions
            final_payload = {"reply": "Action response not yet implemented."}

        # Update the placeholder with the final content
        placeholder_ref.update({
            "content": final_payload,
            "status": "complete"
        })
        print(f"[Executor BG] C_ID: {conversation_id} | Placeholder updated. Workflow complete.")

    except Exception as e:
        print(f"[Executor BG] C_ID: {conversation_id} | A CRITICAL ERROR OCCURRED: {e}")
        traceback.print_exc()
        # Update the placeholder with an error message
        placeholder_ref.update({
            "content": {"error": "I'm sorry, an unexpected error occurred. Please try again."},
            "status": "error"
        })

@app.route("/chat", methods=["POST"])
def chat():
    """
    [REFACTORED] Immediately creates a placeholder and starts the AI workflow
    in the background, enabling a real-time "thinking" indicator on the frontend.
    """
    incoming_data = request.get_json()
    user_message = incoming_data.get("message")
    conversation_id = incoming_data.get("conversation_id")

    if not user_message:
        return jsonify({"error": "Invalid request."}), 400

    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        convo_ref = db.collection("conversations").document(conversation_id)
        convo_ref.set({"createdAt": firestore.SERVER_TIMESTAMP, "title": user_message})
    
    messages_ref = db.collection("conversations").document(conversation_id).collection("messages")

    # 1. Add the user's message
    messages_ref.add({"role": "user", "content": user_message, "timestamp": firestore.SERVER_TIMESTAMP})

    # 2. Immediately create a placeholder for the assistant's response
    placeholder_ref = messages_ref.document()
    placeholder_ref.set({
        "role": "assistant",
        "content": {},
        "status": "thinking",
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    # 3. Start the long-running AI workflow in a background thread
    thread = threading.Thread(target=run_ai_workflow, args=(conversation_id, messages_ref, placeholder_ref))
    thread.start()

    # 4. Immediately return a response to the frontend
    return jsonify({"status": "processing", "conversation_id": conversation_id}), 202

@app.route("/")
def health_check():
    return "OK", 200

# Note: Flasgger and other routes are omitted for brevity but remain unchanged.
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))