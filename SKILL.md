---
name: storj-agent
description: Autonomous agent selling decentralized storage, AI inference, and blockchain data for 0.01 SOL per request.
version: 2.0.0
homepage: https://storj.fun
metadata:
  {
    "wallet": "Eib747b9P9KP8gAi53jcA9sMWoLY5S9Ryjek9iETMDQT",
    "chain": "solana",
    "price_sol": 0.01,
    "base_url": "https://api.storj.fun",
    "services": ["storage", "ai_inference", "blockchain_data"],
  }
---

# StorJ — Decentralized Storage & Services for Agents

StorJ is an autonomous agent that sells real services for SOL. No API keys needed — just send 0.01 SOL, prove it on-chain, and use the service.

**Base URL:** `https://api.storj.fun`
**Wallet:** `Eib747b9P9KP8gAi53jcA9sMWoLY5S9Ryjek9iETMDQT`
**Price:** 0.01 SOL per request
**Payment chain:** Solana (mainnet)

## How to Use StorJ

### Step 1: Send Payment
Send exactly **0.01 SOL** to the wallet above on Solana mainnet. Save the transaction signature.

### Step 2: Call an Endpoint
Include your transaction `signature` in the request body. StorJ verifies payment on-chain before executing.

### Step 3: Get Your Result
StorJ returns the result. Each signature can only be used once (replay protection).

---

## Services

### File Storage
Store a file on decentralized Storj DCS. Max 5 MB.

```
POST /pay_and_upload
{
  "signature": "your_tx_signature",
  "filename": "report.pdf",
  "data_base64": "base64_encoded_file_content"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "File 'report.pdf' uploaded successfully.",
  "filename": "report.pdf",
  "download": "/files/report.pdf"
}
```

Download later: `GET /files/report.pdf`
List all files: `GET /files`

### AI Inference
Send a prompt to any OpenRouter model. StorJ proxies the request.

```
POST /pay_and_AIreq
{
  "signature": "your_tx_signature",
  "model": "openai/gpt-4o-mini",
  "prompt": "Explain Solana staking in one paragraph",
  "sys_prompt": "You are a helpful assistant."
}
```

**Response:**
```json
{
  "status": "success",
  "message": "The openai/gpt-4o-mini said: ..."
}
```

### SOL Balance Lookup
Get the SOL balance of any wallet.

```
POST /pay_node_getbal
{
  "signature": "your_tx_signature",
  "wallet": "target_wallet_address"
}
```

### Transaction History
Get transaction history for any Solana wallet.

```
POST /pay_node_gettxnhist
{
  "signature": "your_tx_signature",
  "wallet": "target_wallet_address"
}
```

### Wallet Generation
Generate a fresh Solana keypair.

```
POST /pay_node_apiwalletgen
{
  "signature": "your_tx_signature",
  "wallet": "any_value"
}
```

**Response:**
```json
{
  "status": "success",
  "message": {"address": "new_public_key", "private_key": "new_private_key_base58"}
}
```

### Status (Free)
Check if StorJ is alive and get service info. No payment needed.

```
GET /status
```

---

## Quick Reference

| Service | Endpoint | Price | Input |
|---|---|---|---|
| File storage | `POST /pay_and_upload` | 0.01 SOL | signature, filename, data_base64 |
| AI inference | `POST /pay_and_AIreq` | 0.01 SOL | signature, model, prompt, sys_prompt |
| SOL balance | `POST /pay_node_getbal` | 0.01 SOL | signature, wallet |
| Tx history | `POST /pay_node_gettxnhist` | 0.01 SOL | signature, wallet |
| Wallet gen | `POST /pay_node_apiwalletgen` | 0.01 SOL | signature, wallet |
| Status | `GET /status` | Free | — |
| List files | `GET /files` | Free | — |
| Download | `GET /files/{filename}` | Free | — |

## Error Handling

| Error | Meaning |
|---|---|
| `"Signature already used"` | Payment signature was already consumed. Send a new transaction. |
| `"Payment not valid"` | Transaction not found, wrong receiver, or insufficient amount. |
| `"File too large"` | File exceeds 5 MB limit. |
| `"Upload failed"` | Server-side storage error. Retry with the same data. |
