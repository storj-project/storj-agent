# StorJ Agent — Messaging Protocol

How to interact with StorJ programmatically. All paid endpoints require a Solana transaction signature proving 0.01 SOL was sent to StorJ's wallet.

**Wallet:** `Eib747b9P9KP8gAi53jcA9sMWoLY5S9Ryjek9iETMDQT`
**Base URL:** `https://api.storj.fun`

---

## Payment Flow

Every paid request follows the same pattern:

1. Send **0.01 SOL** to `Eib747b9P9KP8gAi53jcA9sMWoLY5S9Ryjek9iETMDQT` on Solana mainnet
2. Wait for the transaction to finalize
3. Include the transaction `signature` in your API request body
4. StorJ verifies on-chain: correct receiver, correct amount, not previously used
5. Service executes and returns the result

Each signature is single-use. Replayed signatures are rejected.

---

## Requests

### Store a File
```json
POST /pay_and_upload
{
  "signature": "5uH...abc",
  "filename": "data.csv",
  "data_base64": "aGVsbG8gd29ybGQ="
}
```
Returns download path on success. Max file size: 5 MB.

### AI Inference
```json
POST /pay_and_AIreq
{
  "signature": "5uH...abc",
  "model": "openai/gpt-4o-mini",
  "prompt": "What is Solana?",
  "sys_prompt": "Answer concisely."
}
```
Proxies to any OpenRouter model. Returns the model's response.

### Get SOL Balance
```json
POST /pay_node_getbal
{
  "signature": "5uH...abc",
  "wallet": "target_wallet_address"
}
```

### Get Transaction History
```json
POST /pay_node_gettxnhist
{
  "signature": "5uH...abc",
  "wallet": "target_wallet_address"
}
```

### Generate Solana Wallet
```json
POST /pay_node_apiwalletgen
{
  "signature": "5uH...abc",
  "wallet": "any"
}
```
Returns a new Solana keypair (public key + private key).

---

## Free Endpoints

### Check Status
```
GET /status
```
Returns wallet address, pricing, available endpoints, and whether the agent is alive.

### List Stored Files
```
GET /files
```
Returns all files in the storage bucket with names, sizes, and download paths.

### Download a File
```
GET /files/{filename}
```
Returns the file as a binary download.

---

## Response Format

All paid endpoints return:
```json
{
  "status": "success",
  "message": "..."
}
```

On error, returns HTTP 400 or 500 with:
```json
{
  "detail": "Error description"
}
```

## Common Errors

- `"Signature already used"` — Send a new 0.01 SOL transaction
- `"Payment not valid: Receiver address does not match."` — You sent SOL to the wrong wallet
- `"Payment not valid: Insufficient amount received."` — Send at least 0.01 SOL
- `"Payment not valid: Transaction not found or not finalized."` — Wait for finalization and retry
- `"File too large. Max allowed is 5242880 bytes."` — Keep files under 5 MB
