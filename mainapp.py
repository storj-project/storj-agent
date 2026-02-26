from dotenv import load_dotenv; load_dotenv()
import os
from blockchain import blockchain
from management.StorjAgent import StorjAgent
from subagents import employees
from services.tasking import generate_tweet, upload_file_rclone, generate_new_tweet_prompt_from_openrouter, query_openrouter
import asyncio
from supabase import create_client, Client


import tweepy
import requests

OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
CONSUMER_KEY = os.getenv("TWITTER_CONSUMER_KEY", "")
CONSUMER_SECRET = os.getenv("TWITTER_CONSUMER_SECRET", "")
ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "")
BEARER = os.getenv("TWITTER_BEARER_TOKEN", "")
V2_KEY = "REDACTED"

# Supabase Credentials
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_TABLE = "paid_signatures"  # Table where we store paid signatures

# Storage Configuration
STORJ_GATEWAY = "https://link.storjshare.io/s/firstbucket"
STORJ_ACCESS_KEY = os.getenv("STORJ_ACCESS_KEY", "")
STORJ_ENDPOINT = "https://eu1.gateway.storjshare.io"
BUCKET_NAME = "firstbucket"


def post_tweet_v2(message: str) -> str:

    # Initialize the Tweepy Client for Twitter API v2
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_SECRET
    )

    # Post the tweet
    response = client.create_tweet(text=message)
    return response

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import base64

# Configuration
YOUR_WALLET = "Eib747b9P9KP8gAi53jcA9sMWoLY5S9Ryjek9iETMDQT"
EXPECTED_AMOUNT = 0.01
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB max

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

paid_signatures = set()

# ----- Utility Functions -----

async def scheduled_tweet_generation():
    """
    This function runs every 3 hours to:
    1. Call the prompter to generate a new tweet prompt.
    2. Generate a tweet from that prompt.
    3. Post the tweet.
    """
    print("INSIDE SCHEDULED",flush=True)
    while True:
        try:
            print("Fetching new tweet prompt...")
            tweet_prompt = generate_new_tweet_prompt_from_openrouter()
            print(f"Generated prompt: {tweet_prompt}",flush=True)

            await asyncio.sleep(500)

            tweet = generate_tweet(tweet_prompt)
            print(f"Generated tweet: {tweet}",flush=True)

            post_tweet_v2(tweet)
            print(f"Tweet posted successfully!",flush=True)

        except Exception as e:
            print(f"Tweet scheduler error: {e}",flush=True)

        print("Waiting for 3 hours...",flush=True)
        await asyncio.sleep(1800)  # 30 minutes

async def load_signatures():
    """Load paid signatures from Supabase."""
    global paid_signatures
    response = supabase.table(SUPABASE_TABLE).select("signature").execute()
    print(response,flush=True)
    for record in response.data:
        paid_signatures.add(record["signature"])
    return response.data if response.data else None


async def save_signature(signature: str):
    """Save a verified signature to Supabase and local set."""
    global paid_signatures
    response = supabase.table(SUPABASE_TABLE).upsert({"signature": signature}).execute()
    paid_signatures.add(signature)
    return response.data[0] if response.data else None


def _verify_payment(signature):
    """Helper to verify SOL payment, returns (valid, msg)."""
    result = blockchain.verify_sol_payment(signature, YOUR_WALLET, EXPECTED_AMOUNT)
    if isinstance(result, tuple):
        return result
    return result, ""


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Load previous signatures from Supabase when the app starts
@app.on_event("startup")
async def startup_event():
    print("Loading signatures from Supabase...",flush=True)
    await load_signatures()
    asyncio.create_task(scheduled_tweet_generation())


# ----- Request Models -----
class PayAndUploadRequest(BaseModel):
    signature: str
    filename: str
    data_base64: str

class PayAndAIRequest(BaseModel):
    signature: str
    model: str
    prompt: str
    sys_prompt: str

class PayNodeReq(BaseModel):
    signature: str
    wallet: str


# ----- Endpoints -----

@app.get("/status")
async def status():
    """Service discovery endpoint. Returns wallet, price, and availability."""
    return {
        "agent": "StorJ",
        "status": "alive",
        "wallet": YOUR_WALLET,
        "price_sol": EXPECTED_AMOUNT,
        "max_file_bytes": MAX_FILE_SIZE_BYTES,
        "bucket": BUCKET_NAME,
        "endpoints": {
            "upload": "POST /pay_and_upload",
            "ai": "POST /pay_and_AIreq",
            "txn_history": "POST /pay_node_gettxnhist",
            "balance": "POST /pay_node_getbal",
            "wallet_gen": "POST /pay_node_apiwalletgen",
            "status": "GET /status",
            "files": "GET /files",
            "download": "GET /files/{filename}",
        },
    }


@app.get("/files")
async def list_files():
    """List all uploaded files in the Storj bucket."""
    import subprocess
    from pathlib import Path

    rclone_dir = Path("/tmp")
    result = subprocess.run(
        ["rclone", "lsjson", "storjy:firstbucket"],
        cwd=rclone_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {result.stderr}")

    import json
    try:
        files = json.loads(result.stdout)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to parse file listing")

    return {
        "bucket": BUCKET_NAME,
        "files": [
            {
                "name": f["Name"],
                "size": f.get("Size", 0),
                "modified": f.get("ModTime", ""),
                "download": f"/files/{f['Name']}",
            }
            for f in files
            if not f.get("IsDir", False)
        ],
    }


@app.get("/files/{filename}")
async def download_file(filename: str):
    """Download a file from the Storj bucket."""
    import subprocess
    import tempfile
    from pathlib import Path
    from fastapi.responses import FileResponse

    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    rclone_dir = Path("/tmp")
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / safe_name

    result = subprocess.run(
        ["rclone", "copy", f"storjy:firstbucket/{safe_name}", temp_dir],
        cwd=rclone_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0 or not temp_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    return FileResponse(
        path=str(temp_path),
        filename=safe_name,
        media_type="application/octet-stream",
    )


@app.post("/pay_and_upload")
async def pay_and_upload(req: PayAndUploadRequest):
    global paid_signatures

    # Step 1: Reload signatures from DB (fresh state)
    await load_signatures()

    # Step 2: Check for replay (reject if already used)
    if req.signature in paid_signatures:
        raise HTTPException(status_code=400, detail="Signature already used")

    # Step 3: Verify SOL payment on-chain
    valid, msg = _verify_payment(req.signature)

    if not valid:
        raise HTTPException(status_code=400, detail=f"Payment not valid: {msg}")

    # Step 4: Save signature ONLY after verification passes
    await save_signature(req.signature)

    print(paid_signatures, flush=True)

    # Step 5: Decode base64 to bytes
    try:
        file_bytes = base64.b64decode(req.data_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 file data")

    # Step 6: Check max file size
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max allowed is {MAX_FILE_SIZE_BYTES} bytes."
        )

    # Step 7: Upload file to Storj via rclone
    success, upload_msg = upload_file_rclone(req.data_base64, req.filename)

    if success:
        return {
            "status": "success",
            "message": f"File '{req.filename}' uploaded successfully.",
            "filename": req.filename,
            "download": f"/files/{req.filename}",
        }
    else:
        raise HTTPException(status_code=500, detail=f"Upload failed: {upload_msg}")

@app.post("/pay_and_AIreq")
async def pay_and_request(req: PayAndAIRequest):
    global paid_signatures

    await load_signatures()

    # Prevent replay attacks
    if req.signature in paid_signatures:
        raise HTTPException(status_code=400, detail="Signature already used")

    valid, msg = _verify_payment(req.signature)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Payment not valid: {msg}")

    await save_signature(req.signature)

    output = query_openrouter(
        sys_prompt=req.sys_prompt,
        user_prompt=req.prompt,
        model=req.model
    )

    if output is not None:
        return {"status": "success", "message": f"The {req.model} said: {output}"}
    else:
        raise HTTPException(status_code=500, detail="AI Request failed")

# ----- Node Endpoints -----
@app.post("/pay_node_gettxnhist")
async def pay_and_txnhist(req: PayNodeReq):
    global paid_signatures
    await load_signatures()

    if req.signature in paid_signatures:
        raise HTTPException(status_code=400, detail="Signature already used")

    valid, msg = _verify_payment(req.signature)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Payment not valid: {msg}")

    await save_signature(req.signature)

    output = blockchain.api_get_txn_history(address=req.wallet)

    if output is not None:
        return {"status": "success", "message": output}
    else:
        raise HTTPException(status_code=500, detail="Transaction history request failed")

@app.post("/pay_node_getbal")
async def pay_and_getbal(req: PayNodeReq):
    global paid_signatures
    await load_signatures()

    if req.signature in paid_signatures:
        raise HTTPException(status_code=400, detail="Signature already used")

    valid, msg = _verify_payment(req.signature)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Payment not valid: {msg}")

    await save_signature(req.signature)

    output = blockchain.api_get_bal(address=req.wallet)

    if output is not None:
        return {"status": "success", "message": output}
    else:
        raise HTTPException(status_code=500, detail="Balance request failed")

@app.post("/pay_node_apiwalletgen")
async def pay_and_wallgen(req: PayNodeReq):
    global paid_signatures
    await load_signatures()

    if req.signature in paid_signatures:
        raise HTTPException(status_code=400, detail="Signature already used")

    valid, msg = _verify_payment(req.signature)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Payment not valid: {msg}")

    await save_signature(req.signature)

    output = blockchain.api_wallet_gen()

    if output is not None:
        return {"status": "success", "message": output}
    else:
        raise HTTPException(status_code=500, detail="Wallet generation failed")

if __name__ == "__main__":
    print("Starting Storj...",flush=True)

    async def run():
        storj = StorjAgent()
        storj.spawn_subagent()
        storj.spawn_subagent()
        storj.spawn_subagent()
        storj.spawn_subagent()

        while True:
            storj.run()
            blockchain.generate_wallets()
            await asyncio.sleep(60)

    asyncio.run(run())
