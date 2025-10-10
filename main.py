"""
Vibe Coder Backend Orchestrator - v2.0 (Planning Agent)

This service acts as the central "Project Manager" agent. It implements the
"Triage" and "Plan" steps of the core conversational loop. It classifies a
user's intent and, if it's a task request, calls the architectFlow to
generate a plan.
"""

import os
from flask import Flask, request, jsonify
import requests

# Create the web server application
app = Flask(__name__)

# Define the URLs for our AI "Department Heads"
TASK_CLASSIFIER_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/taskClassifier"
ARCHITECT_URL = "https://australia-southeast1-vibe-agent-final.cloudfunctions.net/architect"

@app.route("/chat", methods=["POST"])
def chat():
    """
    This endpoint orchestrates the Triage -> Plan workflow.
    """

    # 1. Get the user's message from the request.
    incoming_data = request.get_json()
    if not incoming_data or "message" not in incoming_data:
        return jsonify({"error": "Invalid request: 'message' key is required."}), 400
    
    user_message = incoming_data["message"]
    print(f"[Orchestrator] Received user message: '{user_message}'")
    
    try:
        # 2. TRIAGE STEP: Call the Task Classifier to get the user's intent.
        print("[Orchestrator] Calling Task Classifier...")
        classifier_payload = {"data": user_message}
        response = requests.post(TASK_CLASSIFIER_URL, json=classifier_payload)
        response.raise_for_status()
        
        intent = response.json().get("result")
        print(f"[Orchestrator] Received intent: '{intent}'")
        
        # 3. ORCHESTRATE: Decide what to do based on the intent.
        if intent == "task_request":
            # 4. PLAN STEP: If it's a task, call the Architect to get a plan.
            print("[Orchestrator] Calling Architect...")
            architect_payload = {"data": user_message}
            plan_response = requests.post(ARCHITECT_URL, json=architect_payload)
            plan_response.raise_for_status()
            
            # The architect returns a full plan object.
            plan = plan_response.json().get("result")
            print(f"[Orchestrator] Received plan: {plan}")
            
            # Return the structured plan to the user.
            return jsonify({"plan": plan})
            
        elif intent == "chitchat":
            response_message = "TRIAGE: Intent recognized as 'chitchat'. Hello to you too!"
            return jsonify({"reply": response_message})
            
        elif intent == "clarification":
            response_message = "TRIAGE: Intent recognized as 'clarification'. I will provide more details shortly."
            return jsonify({"reply": response_message})
            
        else:
            response_message = "TRIAGE: Could not determine intent. Awaiting further instruction."
            return jsonify({"reply": response_message})
        
    except requests.exceptions.RequestException as e:
        print(f"[Orchestrator] Error during AI service call: {e}")
        return jsonify({"error": "Failed to communicate with the AI service."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))