"""
Vibe Coder Backend Orchestrator - v9.1 (Unified Brain Executor v2)

This version updates the executor logic to align with the AI Engine's new,
simpler z.enum-based DecisionSchema.
"""

import os
import uuid
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from google.cloud import firestore

# --- Initialization ---
app = Flask(__name__)
CORS(app, origins=["https://vibe-agent-phoenix.web.app"])
db = firestore.Client()

# --- AI Service Endpoints ---
PROJECT_MANAGER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/projectManager"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"
FRONTEND_ENGINEER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/frontendEngineer"

@app.route("/chat", methods=["POST"])
def chat():
    """
    This endpoint is the "Dumb Executor." It loads history, calls the brain,
    and executes the brain's decision.
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
        conversation = {"messages": []}
        conversation_ref = db.collection("conversations").document(conversation_id)

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

        if action == "reply_to_user":
            response_payload = {"reply": decision.get("text")}

        elif action == "call_architect":
            print(f"[Executor] C_ID: {conversation_id} | Executing: Call Architect...")
            architect_payload = {"data": decision.get("task")}
            plan_response = requests.post(ARCHITECT_URL, json=architect_payload)
            plan_response.raise_for_status()
            plan = plan_response.json().get("result")
            
            conversation["messages"].append({"role": "assistant", "content": f"I have generated a plan: {plan}"})
            
            print(f"[Executor] C_ID: {conversation_id} | Plan received. Calling brain again for synthesis...")
            pm_payload_2 = {"data": conversation["messages"]}
            pm_response_2 = requests.post(PROJECT_MANAGER_URL, json=pm_payload_2)
            pm_response_2.raise_for_status()
            final_decision = pm_response_2.json().get("result")
            
            response_payload = {"reply": final_decision.get("text"), "plan": plan}

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

# Health check and other endpoints remain the same
# ... (omitted for brevity)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))