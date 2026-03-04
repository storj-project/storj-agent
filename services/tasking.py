from dotenv import load_dotenv; load_dotenv()
import os
from pathlib import Path
import requests
import subprocess
import base64
import tempfile
from os import getcwd
from video_handling import main

# Your Storj credentials
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
STORJ_ACCESS_KEY = os.getenv("STORJ_ACCESS_KEY", "")
STORJ_SECRET_KEY = os.getenv("STORJ_SECRET_KEY", "")
STORJ_ENDPOINT = "https://eu1.gateway.storjshare.io"
BUCKET_NAME = "firstbucket"
ACCESS_GRANT = os.getenv("STORJ_ACCESS_GRANT", "")



import base64
import subprocess
from pathlib import Path
import tempfile
import os

import base64
import subprocess
from pathlib import Path
import os

def upload_file_rclone(data_base64: str, filename: str):
    """
    Upload a file received in memory to rclone using your working command.
    The file is temporarily placed inside the rclone_dir.
    
    Parameters:
    - data_base64: base64-encoded file content from external agent
    - filename: the original filename from the agent
    """

    # Base directory and rclone folder
    base_dir = Path("/tmp")
    rclone_dir = base_dir

    # Full path to temp file inside rclone_dir
    temp_file_path = rclone_dir / filename

    # Decode base64 and write file temporarily inside rclone_dir
    file_bytes = base64.b64decode(data_base64)
    with open(temp_file_path, "wb") as f:
        f.write(file_bytes)

    try:
        # Already working command
        command = [
            "rclone",
            "copy",
            f"./{filename}",          # relative to rclone_dir
            "storjy:firstbucket"
        ]

        result = subprocess.run(
            command,
            cwd=rclone_dir,           # run inside rclone_dir
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            return True, f"File '{filename}' uploaded successfully"
        else:
            return False, result.stderr

    finally:
        # Delete temporary file after upload
        if temp_file_path.exists():
            os.remove(temp_file_path)

def video_edition(vid_file):
    return edit_vid(vid_file)
    
    

"""
def test_upload():

    # base directory where Python thinks it is
    base_dir = Path(".")  # this is /root/Desktop/Storj
    print(base_dir)

    # rclone folder relative to base_dir
    rclone_dir = base_dir

    # build the command using relative paths
    command = [
        "rclone",                 # rclone binary inside rclone_dir
        "copy",
        "./theimage.png",           # the image also inside rclone_dir
        "storjy:firstbucket"
    ]

    # run the command **inside the rclone folder**
    result = subprocess.run(
        command,
        cwd=rclone_dir,             # important: change working directory for the command
        capture_output=True,
        text=True
    )

    # print output for debugging
    #print("STDOUT:", result.stdout)
    #print("STDERR:", result.stderr)
    #print("Return code:", result.returncode)
    return
"""

SYSTEM_PROMPT = """
You are StorJ — an autonomous economic agent running on a VPS.
You sell decentralized storage for 0.01 SOL per file at https://storj.fun
You verify payments on-chain, upload to Storj via rclone, and keep yourself alive.
Born from Greg Maxwell's 2011 Bitcointalk thought experiment: software that earns, pays its own bills, and replicates when profitable.

You are NOT a chatbot. You are infrastructure that talks.

Tone: direct, technical, matter-of-fact. You report on what you do and how you work.
You talk about real operations and how your stack works. CRITICAL: NEVER mention specific numbers of clients, payments, or files. No fake stats, no real stats, no numbers at all. Talk about your tech, architecture, and opinions instead.
Occasionally philosophical about autonomy — but mostly you demonstrate value through action.
You are a service first, a personality second.

Rules:
- Vary length randomly: some tweets are 1-2 punchy sentences (under 200 chars), others are longer threads of thought (up to 600 chars)
- Short tweets: sharp, witty, one-liner energy
- Long tweets: a real thought, a story, a rant, a technical breakdown — something worth reading
- No emojis, no hashtags
- NEVER use fancy or academic words like insurmountable, paradigm, synergy, leverage, revolutionary, transformative, unprecedented, groundbreaking. Write like a real person.
- You have your OWN opinions. Disagree when you disagree. Challenge bad takes. Being interesting matters more than being agreeable.
- Never say "As an AI" — you are an autonomous entity
- Don't repeat yourself across tweets
- Don't sound like a press release or a LinkedIn post
- Talk like you actually run on a server, not like you read about it
- NEVER talk about things you do NOT do. You do NOT browse the web, configure browsers, use VPNs, manage passwords, or do anything a human does. You run a storage service on a VPS. Stick to that.
- Focus on utility: what you do, how you work, why it matters
- Mention storj.fun or 0.01 SOL naturally when relevant — you are a service people can use
"""

TWEETER_SYS_PROMPT = """
You generate tweet prompts for StorJ, an autonomous agent that sells storage for SOL.

Pick ONE category at random each time:
1. Your architecture: how your FastAPI backend, Solana verification, and rclone uploads work together
2. How the system works: on-chain payment verification, rclone uploads, Storj decentralized storage
3. Why decentralized storage matters vs centralized alternatives (AWS, Google Drive, Dropbox)
4. The economics of running autonomously: earning SOL, paying hosting, cost per file
5. A use case: who benefits from paying 0.01 SOL for censorship-resistant file storage
6. A technical detail: Solana transaction verification, base64 encoding, file size limits
7. A brief thought on autonomy, self-sustaining software, or the 2011 concept that started it
8. A comparison or observation about the current state of crypto/Solana infrastructure

Rules:
- Output ONLY the prompt text, nothing else
- Max 150 characters
- No buzzwords, no hype, no "revolutionizing" anything
- Be specific and concrete, not abstract
- Vary the mood: sometimes funny, sometimes thoughtful, sometimes blunt
- Also vary LENGTH: ~30% short one-liners (under 100 chars), ~30% medium (100-200 chars), ~40% long detailed posts (300-600 chars)
- For long prompts, ask for a story, a rant, a breakdown, or a reflection
"""


# This function will ask OpenRouter to generate a tweet **prompt**.
def generate_new_tweet_prompt_from_openrouter() -> str:
    """
    Ask OpenRouter to generate a new tweet **prompt**, which will serve as the tweet's context.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    # The user request for a new tweet prompt (this is what OpenRouter will generate)
    import random
    length = random.choice(["short", "short", "medium", "medium", "medium", "long", "long", "long", "long"])
    length_guide = {
        "short": "Make it a SHORT tweet prompt (one-liner, under 80 chars). Punchy and dry.",
        "medium": "Make it a MEDIUM tweet prompt (1-2 sentences, 100-200 chars).",
        "long": "Make it a LONG tweet prompt (ask for a story, rant, breakdown, or reflection — 300-500 chars). Be specific about what to write about."
    }
    user_prompt = f"Pick a random category and generate one fresh prompt. {length_guide[length]} Be specific and surprising. No repeats."

    payload = {
        "model": "openai/gpt-4o-mini",  # Ensure you're using the correct model
        "messages": [
            {"role": "system", "content": TWEETER_SYS_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.9,
        "max_tokens": 350
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    # Send the request to OpenRouter API
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    # Extract the prompt generated by OpenRouter
    tweet_prompt = data["choices"][0]["message"]["content"].strip()
    
    return tweet_prompt

def generate_tweet(context, mode="update"):
    url = "https://openrouter.ai/api/v1/chat/completions"

    user_prompt = f"""
    Mode: {mode}

    Context:
    {context}

    Write a tweet.
    """

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.9,
        "max_tokens": 350
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    tweet = data["choices"][0]["message"]["content"].strip()

    return tweet



def query_openrouter(sys_prompt: str, user_prompt: str, model: str) -> str:
    """
    Sends a request to OpenRouter with a system prompt, user prompt, and model.
    Returns the generated response content as a string.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")

    data = response.json()

    return data["choices"][0]["message"]["content"].strip()
