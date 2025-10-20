"""
Vibe Coder Backend Orchestrator - v14.1 (CORS Hotfix)

This version applies a critical hotfix to the CORS policy, whitelisting the
new, unified frontend URL (vibe-agent-final.web.app) to resolve the
Cross-Origin Resource Sharing error.
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

# [FIXED] Updated the origin to our new, unified frontend URL.
CORS(app, origins=["https://vibe-agent-final.web.app"])

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
        
        # We need to get the messages from the subcollection for the prompt
        messages_snapshot = messages_ref.order_by("timestamp").get()
        messages_for_prompt = [msg.to_dict() for msg in messages_snapshot]

        print(f"[Executor BG] C_ID: {conversation_id} | Calling PM Brain...")
        pm_payload = {"data": messages_for_prompt}
        pm_response = requests.post(PROJECT_MANAGER_URL, json=pm_payload)
        pm_response.raise_for_status()
        decision = pm_response.json().get("result")
        print(f"[Executor BG] C_ID: {conversation_id} | Brain's decision: {decision}")

        action = decision.get("action")
        final_payload = {}
        
        if action == "call_architect":
            print(f"[Executor BG] C_ID: {conversation_id} | Executing: Call Architect...")
            architect_payload = {"data": decision.get("task")}
            plan_response = requests.post(ARCHITECT_URL, json=architect_payload)
            plan_response.raise_for_status()
            plan = plan_response.json().get("result")

            # Get the current messages again to include the intermediate one
            current_messages_snapshot = messages_ref.order_by("timestamp").get()
            current_messages = [msg.to_dict() for msg in current_messages_snapshot]
            
            # Add the plan to the history for the presentation step
            current_messages.append({
                "role": "assistant",
                "content": {"reply": decision.get("text"), "plan": plan}
            })

            print(f"[Executor BG] C_ID: {conversation_id} | Plan received. Calling brain for presentation...")
            pm_payload_2 = {"data": current_messages}
            pm_response_2 = requests.post(PROJECT_MANAGER_URL, json=pm_payload_2)
            pm_response_2.raise_for_status()
            final_decision = pm_response_2.json().get("result")
            
            final_payload = {"reply": final_decision.get("text"), "plan": plan, "invoked_agent": "architect"}
        
        elif action == "reply_to_user":
            final_payload = {"reply": decision.get("text")}
            
        else:
            final_payload = {"reply": "Action response not yet implemented."}

        placeholder_ref.update({
            "content": final_payload,
            "status": "complete"
        })
        print(f"[Executor BG] C_ID: {conversation_id} | Placeholder updated. Workflow complete.")

    except Exception as e:
        print(f"[Executor BG] C_ID: {conversation_id} | A CRITICAL ERROR OCCURRED: {e}")
        traceback.print_exc()
        placeholder_ref.update({
            "content": {"error": "I'm sorry, an unexpected error occurred. Please try again."},
            "status": "error"
        })

@app.route("/chat", methods=["POST"])
def chat():
    """
    [REFACTORED] Immediately creates a placeholder and starts the AI workflow.
    """
    incoming_data = request.get_json()
    user_message = incoming_data.get("message")
    conversation_id = incoming_data.get("conversation_id")

    if not user_message:
        return jsonify({"error": "Invalid request."}), 400

    if not conversation_id:
        # Create the conversation document and get its ID
        convo_ref = db.collection("conversations").document()
        convo_ref.set({"createdAt": firestore.SERVER_TIMESTAMP, "title": user_message})
        conversation_id = convo_ref.id
    
    messages_ref = db.collection("conversations").document(conversation_id).collection("messages")

    messages_ref.add({"role": "user", "content": user_message, "timestamp": firestore.SERVER_TIMESTAMP})

    placeholder_ref = messages_ref.document()
    placeholder_ref.set({
        "role": "assistant",
        "content": {},
        "status": "thinking",
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    thread = threading.Thread(target=run_ai_workflow, args=(conversation_id, messages_ref, placeholder_ref))
    thread.start()

    return jsonify({"status": "processing", "conversation_id": conversation_id}), 202

# Health check and API docs routes are unchanged and omitted for brevity
@app.route("/")
def health_check():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))