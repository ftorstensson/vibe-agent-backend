"""
Vibe Coder Backend Orchestrator - v13.0 (The Well-Behaved PM)

This version implements the "Smarter Code Police" state machine.
- It adds a 'conversationState' to Firestore to track the conversation's phase.
- It programmatically enforces the "ask for permission" rule.
- It intelligently overrides and corrects the AI if it attempts to act
  out of turn, ensuring a smooth user experience.
"""

import os
import uuid
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from google.cloud import firestore
from flasgger import Swagger

# --- Initialization ---
app = Flask(__name__)
CORS(app, origins=["https://vibe-agent-phoenix.web.app"])
db = firestore.Client(project="vibe-agent-final")

app.config['SWAGGER'] = {
    'title': 'Vibe Coder Agency API',
    'uiversion': 3,
    'version': '13.0',
    'description': 'The official API for the Vibe Coder Agency Backend Orchestrator.'
}
swagger = Swagger(app)

# --- AI Service Endpoints ---
PROJECT_MANAGER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/projectManager"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"
FRONTEND_ENGINEER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/frontendEngineer"


@app.route("/chat", methods=["POST"])
def chat():
    """
    Handles a user's chat message, orchestrates the AI workflow, and returns the response.
    ---
    tags:
      - Conversations
    parameters:
      - in: body
        name: body
        schema:
          id: ChatRequest
          required:
            - message
          properties:
            message:
              type: string
              description: The user's text message.
            conversation_id:
              type: string
              description: The ID of the existing conversation, if any.
    responses:
      200:
        description: The AI's successful response.
      500:
        description: An internal error occurred.
    """
    incoming_data = request.get_json()
    if not incoming_data or "message" not in incoming_data:
        return jsonify({"error": "Invalid request."}), 400

    user_message = incoming_data["message"]
    conversation_id = incoming_data.get("conversation_id")

    conversation_ref = None
    conversation = None
    if conversation_id:
        conversation_ref = db.collection("conversations").document(conversation_id)
        doc = conversation_ref.get()
        if doc.exists: conversation = doc.to_dict()

    if not conversation:
        conversation_id = str(uuid.uuid4())
        # [NEW] Initialize with state for new conversations
        conversation = {"messages": [], "conversationState": "CLARIFYING"}
        conversation_ref = db.collection("conversations").document(conversation_id)

    # [NEW] State Machine Logic
    current_state = conversation.get("conversationState", "CLARIFYING")
    print(f"[Executor] C_ID: {conversation_id} | Current State: {current_state}")

    # Check if the user is giving permission
    affirmative_responses = ["yes", "yep", "ok", "sounds good", "do it", "perfect"]
    if current_state == "AWAITING_PERMISSION" and any(phrase in user_message.lower() for phrase in affirmative_responses):
        print("[Executor] Permission granted by user. Transitioning to PLANNING.")
        conversation["conversationState"] = "PLANNING"
        current_state = "PLANNING"

    conversation["messages"].append({"role": "user", "content": user_message})

    try:
        print(f"[Executor] C_ID: {conversation_id} | Calling Project Manager Brain...")
        pm_payload = {"data": conversation["messages"]}
        pm_response = requests.post(PROJECT_MANAGER_URL, json=pm_payload)
        pm_response.raise_for_status()
        decision = pm_response.json().get("result")
        print(f"[Executor] C_ID: {conversation_id} | Brain's decision: {decision}")

        action = decision.get("action")
        response_payload = {}

        # --- [NEW] Code Police: Enforce State Rules ---
        if action == "call_architect" and current_state != "PLANNING":
            print(f"[Executor] C_ID: {conversation_id} | OVERRIDE: AI tried to call architect in '{current_state}' state. Correcting.")
            response_payload = {"reply": "That's a great idea! Before I create a plan, I just need your final confirmation. Shall I proceed?"}
            conversation["conversationState"] = "AWAITING_PERMISSION"

        # --- Standard Action Handling ---
        elif action == "reply_to_user":
            response_payload = {"reply": decision.get("text")}
            # Check if the AI is asking for permission
            permission_phrases = ["shall i proceed", "may i have your permission", "shall i draw up a formal plan"]
            if any(phrase in decision.get("text").lower() for phrase in permission_phrases):
                print("[Executor] AI is asking for permission. Transitioning to AWAITING_PERMISSION.")
                conversation["conversationState"] = "AWAITING_PERMISSION"

        elif action == "call_architect":
            print(f"[Executor] C_ID: {conversation_id} | Executing: Call Architect...")
            architect_payload = {"data": decision.get("task")}
            plan_response = requests.post(ARCHITECT_URL, json=architect_payload)
            plan_response.raise_for_status()
            plan = plan_response.json().get("result")
            
            intermediate_message = {"role": "assistant", "content": {"reply": decision.get("text"), "plan": plan}}
            conversation["messages"].append(intermediate_message)

            print(f"[Executor] C_ID: {conversation_id} | Plan received. Calling brain again for presentation...")
            pm_payload_2 = {"data": conversation["messages"]}
            pm_response_2 = requests.post(PROJECT_MANAGER_URL, json=pm_payload_2)
            pm_response_2.raise_for_status()
            final_decision = pm_response_2.json().get("result")
            
            response_payload = {"reply": final_decision.get("text"), "plan": plan}
            # Reset state after planning is complete
            conversation["conversationState"] = "CLARIFYING"

        elif action == "call_engineer":
            response_payload = {"reply": "EXECUTION LOGIC NOT YET IMPLEMENTED."}
        
        else:
            raise ValueError(f"Unknown action from brain: {action}")

        conversation["messages"].append({"role": "assistant", "content": response_payload})
        conversation["lastUpdated"] = firestore.SERVER_TIMESTAMP
        conversation_ref.set(conversation, merge=True)
        
        response_payload["conversation_id"] = conversation_id
        return jsonify(response_payload)

    except Exception as e:
        print(f"[Executor] C_ID: {conversation_id} | A CRITICAL ERROR OCCURRED: {e}")
        traceback.print_exc()
        return jsonify({"error": "An internal error occurred."}), 500

@app.route("/")
def health_check():
    """A simple health check endpoint."""
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))