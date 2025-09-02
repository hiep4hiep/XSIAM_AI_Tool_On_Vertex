#!/usr/bin/env python3
"""
Vertex AI Chat Backend using Python Flask and Google Cloud SDK
"""

import os
import logging
from datetime import datetime
import asyncio
import vertexai
from vertexai import agent_engines
from vertexai.preview import reasoning_engines
from google.adk.sessions import VertexAiSessionService
from dotenv import load_dotenv

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google.cloud import aiplatform
from google.oauth2 import service_account
from google.auth import default
import vertexai
import uuid, threading
import csv, json
import tempfile
import asyncio
import concurrent.futures

from werkzeug.utils import secure_filename


RESULTS_DIR = os.path.join(os.getcwd(), "results")
MAX_CONCURRENCY = 5  # tune based on server and Vertex AI quota
JOB_DIR = os.path.join(os.getcwd(), "job_status")
os.makedirs(JOB_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
load_dotenv()
# Flask app setup
app = Flask(__name__)
CORS(app)

# Init Vertex AI
vertexai.init(
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION"),
)
#session_service = VertexAiSessionService(project=os.getenv("GOOGLE_CLOUD_PROJECT"),location=os.getenv("GOOGLE_CLOUD_LOCATION"))
#AGENT_ENGINE_ID = os.getenv("AGENT_ENGINE_ID")
#agent_engine = agent_engines.get(AGENT_ENGINE_ID)
def save_job_status(job_id, status):
    path = os.path.join(JOB_DIR, f"{job_id}.json")
    with open(path, "w") as f:
        json.dump(status, f)


def load_job_status(job_id):
    path = os.path.join(JOB_DIR, f"{job_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
    

def chat_to_engine(engine_id):
    agent_engine = agent_engines.get(engine_id)
    if not agent_engine:
        return jsonify({"error": "Invalid engine ID"}), 400

    try:
        # Parse request JSON
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        message = data.get('message', '').strip()
        if not message:
            return jsonify({"error": "Message is required"}), 400

        session_id = data.get('session_id')
        if not session_id:
            session = agent_engine.create_session(user_id="web_app")
            session_id = session.get('id')

        logger.info(f"Session {session_id} - Received chat message: {message[:100]}...")

        result = None
        for response in agent_engine.stream_query(
            message=message,
            user_id="web_app",
            session_id=session_id
        ):
            result = response  # assuming the last one is the final result

        if not result:
            return jsonify({"error": "No response from agent engine"}), 500

        content_parts = result.get("content", {}).get("parts", [])
        text = content_parts[0].get("text") if content_parts else None

        if text:
            logger.info(f"Returning response...")
            return jsonify({
                "response": text,
                "session_id": session_id,
                "timestamp": result.get("timestamp")
            })
        else:
            error_msg = result.get("error", "Unknown error")
            logger.info(f"Returning error: {error_msg}")
            return jsonify({
                "error": error_msg,
                "timestamp": result.get("timestamp")
            }), 500

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        return jsonify({
            "error": f"Internal server error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }), 500

def query_agent(msg,engine_id):
    agent_engine = agent_engines.get(engine_id)
    session = agent_engine.create_session(user_id="batch_job")
    session_id = session.get("id")
    result_text = ""
    for response in agent_engine.stream_query(
        message=msg,
        user_id="batch_job",
        session_id=session_id
    ):
        result = response
    return result.get("content").get("parts")[0].get("text", "")


def process_and_save(file_path, job_id, output_filename, engine_id):
    """Background worker: process CSV and save results locally"""
    #agent_engine = agent_engines.get(engine_id)
    try:
        save_job_status(job_id, {"status": "running", "result_url": None, "error": None})
        results = []
        # Load all messages
        with open(file_path, newline='', encoding="utf-8") as infile:
            reader = [row[0].strip() for row in csv.reader(infile) if row]

        # Run queries in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
            futures = {executor.submit(query_agent, msg, engine_id): msg for msg in reader}
            for future in concurrent.futures.as_completed(futures):
                msg = futures[future]
                try:
                    result_text = future.result()
                except Exception as e:
                    result_text = f"ERROR: {str(e)}"
                results.append([msg, result_text])


        # Save results file
        output_path = os.path.join(RESULTS_DIR, output_filename)
        with open(output_path, "w", newline='', encoding="utf-8") as out_csv:
            writer = csv.writer(out_csv)
            writer.writerow(["Input", "Output"])
            for r in results:
                writer.writerow(r)

        save_job_status(job_id, {"status": "completed", "result_url": f"/results/{output_filename}", "error": None})

    except Exception as e:
        save_job_status(job_id, {"status": "failed", "result_url": None, "error": str(e)})


# Routes
@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('.', 'index.html')

@app.route('/api/chat/<engine_key>', methods=['POST'])
def chat(engine_key):
    # Map engine_key to environment variable or direct engine_id
    engine_env_map = {
        "doc": os.getenv("DOC_AGENT_ENGINE_ID"),
        "spl": os.getenv("SPL_AGENT_ENGINE_ID")
    }
    engine_id = engine_env_map.get(engine_key)
    if not engine_id:
        return jsonify({"error": f"Unknown engine '{engine_key}'"}), 404

    return chat_to_engine(engine_id)


@app.route('/api/batch_chat/<engine_key>', methods=['POST'])
def batch_chat(engine_key):
    engine_env_map = {
        "doc": os.getenv("DOC_AGENT_ENGINE_ID"),
        "spl": os.getenv("SPL_AGENT_ENGINE_ID")
    }
    engine_id = engine_env_map.get(engine_key)
    logger.info(engine_id)
    if not engine_id:
        return jsonify({"error": f"Unknown engine"}), 404
    #agent_engine = agent_engines.get(engine_id)
    """Batch chat endpoint: upload CSV -> process each line concurrently -> return CSV"""
    """ Return result directly to user
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
        
        filename = secure_filename(file.filename)

        # Read uploaded CSV (assume first column = prompt)
        messages = []
        reader = csv.reader(file.stream.read().decode("utf-8").splitlines())
        for row in reader:
            if row:
                messages.append(row[0].strip())

        # Async processing
        async def process_message(msg, semaphore):
            async with semaphore:
                try:
                    session = agent_engine.create_session(user_id="batch_job")
                    session_id = session.get("id")

                    result_text = ""
                    for response in agent_engine.stream_query(
                        message=msg,
                        user_id="batch_job",
                        session_id=session_id
                    ):
                        result = response
                    result_text = result.get("content").get("parts")[0].get("text", "")
                    return {"input": msg, "output": result_text}
                except Exception as e:
                    return {"input": msg, "output": f"ERROR: {str(e)}"}

        async def run_batch():
            semaphore = asyncio.Semaphore(5)  # limit concurrency to 5
            tasks = [process_message(m, semaphore) for m in messages]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run_batch())

        # Write results to a temporary CSV
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        with open(temp_file.name, "w", newline='', encoding="utf-8") as out_csv:
            writer = csv.writer(out_csv)
            writer.writerow(["Input", "Output"])
            for r in results:
                writer.writerow([r["input"], r["output"]])

        return send_from_directory(
            directory=os.path.dirname(temp_file.name),
            path=os.path.basename(temp_file.name),
            as_attachment=True,
            download_name=f"batch_results_{filename}"
        )

    except Exception as e:
        logger.error(f"Error in batch_chat endpoint: {e}")
        return jsonify({
            "error": f"Internal server error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }), 500
    """
    """ New version: Save results to a file and return URL """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Empty filename"}), 400

        # Save upload temporarily
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        file.save(tmp_in.name)

        # Define output filename + public URL
        job_id = str(uuid.uuid4())
        output_filename = f"{job_id}.csv"
        output_url = f"/results/{engine_id}/{output_filename}"

        # Start background job
        threading.Thread(
            target=process_and_save,
            args=(tmp_in.name, job_id, output_filename, engine_id),
            daemon=True
        ).start()
        job_status = {
            "status": "pending",
            "result_url": None,
            "error": None
        }
        save_job_status(job_id, job_status)
        return jsonify({
            "job_id": job_id,
            "status_url": f"/api/batch_status/{engine_id}/{job_id}"
        })

    except Exception as e:
        logger.error(f"Error in batch_chat: {e}")
        return jsonify({"error": str(e)}), 500
    
    
@app.route('/api/batch_status/<engine_key>/<job_id>', methods=['GET'])
def batch_status(job_id):
    job = load_job_status(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# Serve result files
@app.route('/results/<engine_key>/<path:filename>')
def download_result(filename):
    return send_from_directory(RESULTS_DIR, filename, as_attachment=True)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "timestamp": datetime.now().isoformat()
    }), 500


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🚀 Starting Vertex AI Chat Server")
    logger.info(f"🌐 Server will run on: http://0.0.0.0:8000")
    logger.info("=" * 50)
    
    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=8000,
        debug=os.getenv('DEBUG', 'false').lower() == 'true'
    )