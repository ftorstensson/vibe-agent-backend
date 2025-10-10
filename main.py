"""
Vibe Coder Backend Orchestrator - v4.0 (Executing Agent)

This service acts as the central "Project Manager" agent. It now implements
the full, end-to-end "Triage -> Plan -> Confirm -> Execute" conversational loop.
After a plan is approved, it delegates the first step to the frontendEngineerFlow.
"""

import os
import uuid
from flask import Flask, request, jsonify
import requests

# Create the web server application
app = Flask(__name__)

# --- In-Memory State Management (Proof of Tool Simplification) ---
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
        # --- STATE MACHINE ---
        if conversation_state == "awaiting_plan_approval":
            # --- CONFIRM STEP ---
            if user_message.lower() == "yes":
                print(f"[Orchestrator] C_ID: {conversation_id} | Plan approved. Beginning execution.")
                
                # --- EXECUTE STEP ---
                plan = conversation.get("plan")
                if not plan or not plan.get("steps"):
                    return jsonify({"error": "Cannot execute: No plan found in conversation."}), 500
                
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
                    "reply": "CONFIRMATION: Plan not approved. Please provide feedback or say 'yes' to approve.",
                    "conversation_id": conversation_id,
                }
        else:
            # --- TRIAGE & PLAN STEPS ---
            # (This logic remains the same as before)
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
                    "reply": "Here is the plan I have generated. Please review and respond with 'yes' to approve.",
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