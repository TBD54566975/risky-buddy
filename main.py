from flask import Flask, request, jsonify
import os
import requests
import json
import subprocess
import shlex
import signal
import time

app = Flask(__name__)

# Path to the directory containing the rule files
RULES_DIR = './rules'

# Default model
DEFAULT_MODEL = 'Phi-3-mini-4k-instruct'

# Llamafile details
LLAMAFILE_URL = 'https://huggingface.co/Mozilla/Phi-3-mini-4k-instruct-llamafile/resolve/main/Phi-3-mini-4k-instruct.F16.llamafile?download=true'
LLAMAFILE_NAME = 'Phi-3-mini-4k-instruct.F16.llamafile'
LLAMAFILE_PORT = 9090

# Function to download the llamafile if it does not exist
def download_llamafile():
    if not os.path.exists(LLAMAFILE_NAME):
        print(f'Downloading {LLAMAFILE_NAME}...')
        response = requests.get(LLAMAFILE_URL)
        with open(LLAMAFILE_NAME, 'wb') as file:
            file.write(response.content)
        os.chmod(LLAMAFILE_NAME, 0o755)
        print(f'Download completed and set executable permissions for {LLAMAFILE_NAME}.')

# Function to run the llamafile
def run_llamafile():
    if not os.path.exists(LLAMAFILE_NAME):
        raise FileNotFoundError(f'{LLAMAFILE_NAME} does not exist.')

    print(f'Running {LLAMAFILE_NAME} on port {LLAMAFILE_PORT}...')
    llamafile_process = subprocess.Popen(f'./{LLAMAFILE_NAME} --port {LLAMAFILE_PORT}', 
                                         shell=True, 
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE)
    time.sleep(5)  # Wait for a few seconds to let the server start
    return llamafile_process

# Load rules from disk
def load_rules():
    rules = []
    for filename in os.listdir(RULES_DIR):
        if filename.endswith('.txt'):
            with open(os.path.join(RULES_DIR, filename), 'r') as file:
                rules.append(file.read().strip())
    return rules

# Format the prompt for the LLaMAfile API
def format_prompt(data, rules):
    rules_text = '\n'.join(rules)
    prompt = (
        f"### Rules\n"
        f"{rules_text}\n\n"
        f"### Data\n"
        f"{json.dumps(data, indent=2)}\n\n"
        f"### Task\n"
        f"Based on the rules provided, evaluate the data and return a JSON response with the fields:\n"
        f"- score: one of 'high', 'medium', or 'low'\n"
        f"- justification: a detailed explanation based on the rules and data\n\n"
        f"Ensure the response is formatted as valid JSON without any additional text or explanations."
    )
    return prompt

# Call the LLaMAfile API to score the data
def score_data(model, prompt):
    response = requests.post(f'http://localhost:{LLAMAFILE_PORT}/completion', json={
        'prompt': prompt,
        'n_predict': 150,  # Limit the response length
        'temperature': 0.7,  # Adjust the randomness of the generated text
    })
    response_data = response.json()
    # Extract the JSON content from the response
    response_text = response_data['content'].strip()
    start = response_text.find('{')
    end = response_text.rfind('}') + 1
    if start != -1 and end != -1:
        json_response = response_text[start:end]
    else:
        json_response = '{}'
    return json_response

@app.route('/api/score', methods=['POST'])
def score():
    try:
        data = request.json.get('data')
        model = request.json.get('model', DEFAULT_MODEL)
        
        # Load rules
        rules = load_rules()
        
        # Format the prompt
        prompt = format_prompt(data, rules)
        
        # Get the score from LLaMAfile API
        score = score_data(model, prompt)
        
        # Print the score and any potential error
        print("Score:", score)
        
        return jsonify(json.loads(score))
    except Exception as e:
        error_message = str(e)
        print("Error:", error_message)
        return jsonify({'error': error_message}), 500

if __name__ == '__main__':
    download_llamafile()
    llamafile_process = run_llamafile()
    try:
        app.run(port=8080)
    finally:
        llamafile_process.send_signal(signal.SIGINT)
        llamafile_process.wait()
