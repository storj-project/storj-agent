# StorJ v2 — Autonomous Economic Agent

An autonomous software agent inspired by [Greg Maxwell's 2011 Bitcointalk concept](https://bitcointalk.org/index.php?topic=53855.0): a program that earns cryptocurrency, pays for its own hosting, and replicates when profitable.

## What it does

- Sells decentralized storage for SOL (0.01 SOL per upload, 5 MB max)
- Verifies on-chain Solana payments before accepting files
- Uploads files to Storj via rclone
- Generates and posts tweets autonomously every 3 hours
- Manages subagent workers with performance scoring
- Evolves population: kills underperformers, mutates survivors
- Reinvests profits by spawning new subagents

## Architecture

```
StorjAgent (main)
├── blockchain/       BTC & SOL wallets, balances, transactions, payment verification
├── management/       StorjAgent class: orchestrates subagents, reinvestment, evaluation
├── subagents/        WorkerAgent: skills, strategies, performance scoring
├── services/
│   ├── tasking.py    Tweet generation via OpenRouter, file upload via rclone
│   ├── sales.py      Task execution (Twitter, OpenRouter, Alchemy, Storage)
│   ├── evolution.py  Population evolution: kill weakest, mutate survivors
│   └── survival.py   Hosting payment logic
└── mainapp.py        FastAPI server + scheduled tweet loop + Supabase integration
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Service discovery (wallet, price, availability) |
| GET | `/files` | List all uploaded files |
| GET | `/files/{filename}` | Download a specific file |
| POST | `/pay_and_upload` | Pay SOL + upload file (base64) |

## Setup

1. Clone and install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables (see `.env.example`):
```bash
cp .env.example .env
# Fill in your credentials
```

3. Make sure rclone is configured with your Storj gateway credentials.

4. Run the API server:
```bash
uvicorn mainapp:app --host 0.0.0.0 --port 8000
```

Or run the standalone agent loop:
```bash
python mainapp.py
```

## Environment Variables

| Variable | Purpose |
|---|---|
| `OPENROUTER_KEY` | OpenRouter API key for tweet generation |
| `TWITTER_CONSUMER_KEY` | Twitter API consumer key |
| `TWITTER_CONSUMER_SECRET` | Twitter API consumer secret |
| `TWITTER_ACCESS_TOKEN` | Twitter API access token |
| `TWITTER_ACCESS_SECRET` | Twitter API access token secret |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service key |
| `STORJ_ACCESS_KEY` | Storj S3 gateway access key |
| `STORJ_SECRET_KEY` | Storj S3 gateway secret key |
| `STORJ_ENDPOINT` | Storj S3 gateway endpoint |
| `SOL_WALLET_ADDRESS` | Agent's Solana wallet address |

## How the upload flow works

1. External agent sends SOL to the agent's wallet
2. Agent receives `POST /pay_and_upload` with `{signature, filename, data_base64}`
3. Checks signature hasn't been used before (replay protection via Supabase)
4. Verifies SOL payment on-chain (correct receiver, correct amount, finalized)
5. Saves signature to prevent reuse
6. Decodes and uploads file to Storj via rclone
7. Returns download link

## License

MIT
