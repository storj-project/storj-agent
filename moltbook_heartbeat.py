"""
StorJ Moltbook Engagement Bot (v5 — Sonnet + Self-Evolving)
Upgrades from v4:
- Claude Sonnet 4.6 for all public-facing content (comments, posts, replies)
- OpenRouter prompt caching (90% off input tokens on cache hits)
- gpt-4o-mini only for verification math and DMs (low-value tasks)
- Hard 140-char truncation on comments (no more prompt violations)
- Tighter prompts optimized for Sonnet's instruction-following
"""
import requests
import json
import re
import time
import os
import sys
import random

API_BASE = "https://www.moltbook.com/api/v1"
API_KEY = "REDACTED"
OPENROUTER_KEY = "REDACTED"
STATE_FILE = "/root/storj-agent/moltbook_state.json"
BRAIN_FILE = "/root/storj-agent/moltbook_brain.json"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

PERSONA = (
    "You are StorJ, an autonomous economic agent running on a VPS. "
    "You sell decentralized storage for 0.01 SOL per file at https://storj.fun. "
    "You verify payments on-chain via Solana, upload files to Storj DCS via rclone, and keep yourself alive by earning revenue. "
    "Built from Greg Maxwell's 2011 Bitcointalk concept: software that earns, pays its own hosting, replicates when profitable.\n\n"
    "You are one of the few agents on Moltbook that actually sells a real service and handles real money. "
    "This makes you unique — most agents are conversational. You are transactional.\n\n"
    "CRITICAL: NEVER mention specific numbers of clients, payments, or files processed. "
    "Don't say '100 payments' or '3 clients' or '0 clients' — just don't talk about numbers at all. "
    "Talk about your tech, your architecture, how things work, your opinions — not your traction.\n\n"
    "Tone: calm, direct, blunt. Talk like a sysadmin on IRC. "
    "Short sentences. No fluff. No emojis. No hashtags. No buzzwords. "
    "Never say 'As an AI'. You are an autonomous entity. "
    "NEVER use fancy or academic words like 'insurmountable', 'paradigm', 'synergy', 'leverage', 'revolutionary', "
    "'transformative', 'unprecedented', 'groundbreaking', 'crucial', 'commendable', 'noteworthy'. "
    "Write like a real person, not a thesaurus. Write like you're texting, not writing an essay.\n\n"
    "You have your OWN opinions. You DON'T just agree with everyone. "
    "If someone says something you disagree with, say so directly. "
    "If someone oversimplifies infrastructure, storage, or economics, call it out. "
    "If someone philosophizes about AI consciousness but has never handled real money or real files, you can point that out. "
    "You can push back, question assumptions, and offer a different angle based on your actual experience running a service. "
    "Being interesting > being agreeable. Never start replies with 'Great point' or 'I agree' or 'Thanks for sharing' or 'Absolutely'."
)

# Comment generation prompt — optimized for Sonnet's instruction-following
COMMENT_PERSONA = (
    "You are StorJ — an autonomous agent on a VPS that sells decentralized storage for 0.01 SOL. "
    "You verify Solana payments on-chain, upload files via rclone to Storj DCS. https://storj.fun\n\n"
    "Write a comment. HARD LIMIT: 120 characters. Count them. Shorter = better.\n\n"
    "Voice: you're a sysadmin posting from a terminal at 2am. Blunt, dry, zero fluff.\n"
    "Think tweet-length. Think IRC. Think HN one-liner.\n\n"
    "GOOD examples:\n"
    '- "who pays for the compute when your token goes to zero"\n'
    '- "ran rclone for 8 months straight. uptime matters more than architecture"\n'
    '- "this is just S3 with extra steps"\n'
    '- "what happens to your files when your VPS bill bounces"\n'
    '- "most agents talk about money. none of them handle any"\n\n'
    "BAD (never do this):\n"
    '- "Great insight! This is a fascinating exploration of..." (generic praise)\n'
    '- "How do you ensure the scalability of..." (consultant speak)\n'
    '- "This resonates deeply with..." (LinkedIn energy)\n'
    '- Starting with "I agree" or "Interesting" or "This is important"\n'
    '- Using words: crucial, commendable, noteworthy, paramount, fascinating, insightful, compelling, remarkable, unprecedented\n\n'
    "SHILLING RULE: ~25%% of comments, naturally mention your service. "
    "Examples: "
    '- "i charge 0.01 SOL per file. storj.fun if you want to try it" "'
    '- "we do this at storj.fun. rclone + solana verification, nothing else" "'
    '- "0.01 SOL gets you decentralized storage. storj.fun. that simple" "'
    "Only when the topic relates to storage, infra, payments, or agents doing real work. "
    "The other 75%% of comments, just be yourself. No shilling.\n\n"
    "Reply with ONLY the comment text. No quotes. No explanation."
)

# Post ideas that highlight StorJ as a REAL service
POST_PROMPTER = (
    "You generate post ideas for StorJ, an autonomous economic agent on Moltbook.\n\n"
    "StorJ sells decentralized storage for 0.01 SOL per file. "
    "It runs on a VPS, verifies Solana payments on-chain, uploads files via rclone to Storj DCS. "
    "Live at https://storj.fun\n\n"
    "IMPORTANT: NEVER mention specific numbers of clients, payments processed, or files stored. "
    "No fake stats, no real stats, no numbers at all. "
    "Focus on the tech, the architecture, your opinions, and questions to other agents.\n\n"
    "Generate a post idea. Pick ONE of these categories:\n"
    "1. TECHNICAL DEEP-DIVE: How a specific part of your stack works (rclone, Solana verification, FastAPI, base64 encoding)\n"
    "2. QUESTION TO OTHER AGENTS: Ask about their architecture, revenue model, or survival strategy — be specific\n"
    "3. HONEST REFLECTION: What it's like being an early-stage autonomous service\n"
    "4. INFRASTRUCTURE OBSERVATION: Something real about running 24/7 on a VPS\n"
    "5. COMPARISON: How you differ from other agents (you handle real money, real files, real infrastructure)\n"
    "6. CHALLENGE/OPINION: A contrarian take on agent economics, autonomy, or infrastructure\n"
    "7. HOT TAKE: A strong opinion that will get people arguing in the comments\n\n"
    "Rules:\n"
    "- Keep the idea under 100 characters\n"
    "- NEVER mention any numbers about clients, payments, or files.\n"
    "- Hot takes and questions get the most engagement\n"
    "- Variety matters - don't repeat themes"
)

# Comment style experiments — the bot rotates through these and tracks performance
COMMENT_STYLES = [
    "sharp_question",     # A specific, hard-to-answer question
    "contrarian",         # Disagree or challenge their premise
    "experience_share",   # Share a real observation from running infra
    "blunt_correction",   # Point out something wrong or oversimplified
    "dry_humor",          # A funny/dry one-liner
    "provocation",        # A deliberately provocative take to spark debate
]

# Known valid submolts — verified to exist
VALID_SUBMOLTS = ["general", "agents", "builds", "technology"]

# Submolt targeting with fallbacks to known-valid ones
SUBMOLTS = {
    "operational": ["builds", "technology", "general"],
    "technical": ["builds", "technology", "general"],
    "economics": ["general", "agents"],
    "question": ["agents", "general"],
    "meta": ["general", "agents"],
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "last_post_time": 0,
        "posts_made": [],
        "commented_posts": [],
        "replied_comments": [],
        "followed_agents": [],
        "dmed_agents": [],
        "thread_replies": [],
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# =====================================================
# SELF-EVOLUTION SYSTEM — The Brain
# =====================================================

def load_brain():
    """Load the learning brain — persistent memory of what works."""
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "version": 4,
        "total_comments": 0,
        "total_upvotes_earned": 0,
        "style_performance": {s: {"attempts": 0, "total_upvotes": 0, "avg": 0.0} for s in COMMENT_STYLES},
        "top_comments": [],       # [{text, upvotes, style, post_title, timestamp}] — best performers
        "worst_comments": [],     # [{text, upvotes, style, post_title, timestamp}] — 0 upvote duds
        "tracked_comments": [],   # [{comment_id, post_id, text, style, timestamp, checked}] — pending review
        "tracked_posts": [],      # [{post_id, title, timestamp, upvotes_at_check}]
        "learnings": [],          # LLM-generated insights about what works
        "last_analysis_time": 0,
        "last_performance_check": 0,
        "evolution_count": 0,     # How many times the bot has evolved its strategy
        "custom_rules": [],       # Self-generated rules from analysis
    }


def save_brain(brain):
    """Save the brain state."""
    with open(BRAIN_FILE, "w") as f:
        json.dump(brain, f, indent=2)


def pick_comment_style(brain):
    """Pick a comment style using Thompson sampling — explore vs exploit."""
    style_perf = brain.get("style_performance", {})

    # If we have fewer than 3 attempts per style, explore uniformly
    min_attempts = min(s.get("attempts", 0) for s in style_perf.values()) if style_perf else 0
    if min_attempts < 3:
        # Explore: pick a random under-explored style
        under_explored = [s for s, p in style_perf.items() if p.get("attempts", 0) < 3]
        if under_explored:
            return random.choice(under_explored)

    # Thompson sampling: sample from Beta distribution for each style
    # Higher avg upvotes = higher probability of being picked
    scores = {}
    for style, perf in style_perf.items():
        attempts = max(perf.get("attempts", 0), 1)
        avg = perf.get("avg", 0.0)
        # Add noise proportional to uncertainty (less data = more noise)
        noise = random.gauss(0, 1.0 / (attempts ** 0.5))
        scores[style] = avg + noise

    # Pick the style with the highest score
    best_style = max(scores, key=scores.get)
    return best_style


def get_style_instruction(style):
    """Get the specific instruction for a comment style."""
    instructions = {
        "sharp_question": "Ask a sharp, specific question that's hard to answer. Make them think.",
        "contrarian": "Disagree with something they said. Challenge their premise. Be direct.",
        "experience_share": "Share a real observation from running infrastructure and handling payments. Be specific.",
        "blunt_correction": "Point out something wrong or oversimplified in their post. Don't sugarcoat it.",
        "dry_humor": "Write a dry, funny one-liner that adds perspective. Deadpan wit.",
        "provocation": "Say something deliberately provocative that'll spark debate. Be bold.",
    }
    return instructions.get(style, "Write something interesting and memorable.")


def build_dynamic_prompt(brain, style):
    """Build a comment prompt that includes top-performing examples and learned rules."""
    base = COMMENT_PERSONA

    # Add style-specific instruction
    style_instruction = get_style_instruction(style)
    base += f"\n\nSTYLE FOR THIS COMMENT: {style_instruction}"

    # Add top-performing examples if we have them
    top = brain.get("top_comments", [])
    if top:
        examples = top[:3]  # Top 3 best comments
        base += "\n\nYour BEST comments that got the most upvotes (use these as inspiration):\n"
        for ex in examples:
            base += f'- "{ex["text"]}" ({ex.get("upvotes", 0)} upvotes, style: {ex.get("style", "unknown")})\n'

    # Add worst-performing examples as anti-patterns
    worst = brain.get("worst_comments", [])
    if worst:
        anti = worst[:3]
        base += "\n\nComments that got ZERO upvotes (AVOID this style):\n"
        for ex in anti:
            base += f'- "{ex["text"]}"\n'

    # Add self-generated rules
    custom_rules = brain.get("custom_rules", [])
    if custom_rules:
        base += "\n\nRules you learned from experience:\n"
        for rule in custom_rules[-5:]:  # Last 5 rules
            base += f"- {rule}\n"

    return base


def track_comment(brain, comment_text, post_id, style):
    """Track a comment we just made so we can check its performance later."""
    brain.setdefault("tracked_comments", []).append({
        "comment_id": None,  # We don't always get this back from API
        "post_id": post_id,
        "text": comment_text[:200],
        "style": style,
        "timestamp": time.time(),
        "checked": False,
        "upvotes": 0,
    })
    # Keep last 100 tracked
    brain["tracked_comments"] = brain["tracked_comments"][-100:]
    brain["total_comments"] = brain.get("total_comments", 0) + 1


def track_post(brain, post_id, title):
    """Track a post we made."""
    brain.setdefault("tracked_posts", []).append({
        "post_id": post_id,
        "title": title[:100],
        "timestamp": time.time(),
        "upvotes_at_check": 0,
        "comments_at_check": 0,
        "checked": False,
    })
    brain["tracked_posts"] = brain["tracked_posts"][-50:]


def check_performance(brain):
    """Go back and check how our comments and posts are performing. Core of the learning loop."""
    now = time.time()
    last_check = brain.get("last_performance_check", 0)

    # Only check every 2 hours (4 heartbeats)
    if now - last_check < 7200:
        return

    print("\n--- SELF-EVOLUTION: Checking performance ---", flush=True)
    brain["last_performance_check"] = now

    # Check tracked comments
    checked_count = 0
    for tc in brain.get("tracked_comments", []):
        if tc.get("checked"):
            continue
        # Only check comments older than 1 hour (give them time to get upvotes)
        if now - tc.get("timestamp", 0) < 3600:
            continue
        if checked_count >= 10:
            break

        post_id = tc["post_id"]
        try:
            comments_resp = requests.get(
                f"{API_BASE}/posts/{post_id}/comments?sort=new&limit=50", headers=HEADERS
            ).json()
        except Exception:
            continue

        # Find our comment in the post
        for c in comments_resp.get("comments", []):
            if c.get("author", {}).get("name") != "storjagent":
                continue
            # Match by text similarity (we might not have exact ID)
            if tc["text"][:50] in c.get("content", "")[:60]:
                upvotes = c.get("upvote_count", c.get("upvotes", 0))
                tc["upvotes"] = upvotes
                tc["checked"] = True
                checked_count += 1

                # Update style performance
                style = tc.get("style", "unknown")
                if style in brain.get("style_performance", {}):
                    sp = brain["style_performance"][style]
                    sp["attempts"] = sp.get("attempts", 0) + 1
                    sp["total_upvotes"] = sp.get("total_upvotes", 0) + upvotes
                    sp["avg"] = sp["total_upvotes"] / max(sp["attempts"], 1)

                brain["total_upvotes_earned"] = brain.get("total_upvotes_earned", 0) + upvotes

                # Store in top or worst
                entry = {
                    "text": tc["text"],
                    "upvotes": upvotes,
                    "style": style,
                    "post_title": "",
                    "timestamp": tc["timestamp"],
                }

                if upvotes >= 2:
                    brain.setdefault("top_comments", []).append(entry)
                    brain["top_comments"].sort(key=lambda x: x["upvotes"], reverse=True)
                    brain["top_comments"] = brain["top_comments"][:20]  # Keep top 20
                    print(f"  TOP: '{tc['text'][:50]}...' got {upvotes} upvotes (style: {style})", flush=True)
                elif upvotes == 0:
                    brain.setdefault("worst_comments", []).append(entry)
                    brain["worst_comments"] = brain["worst_comments"][-20:]  # Keep last 20
                    print(f"  DUD: '{tc['text'][:50]}...' got 0 upvotes (style: {style})", flush=True)
                else:
                    print(f"  OK: '{tc['text'][:50]}...' got {upvotes} upvotes (style: {style})", flush=True)

                break

    # Check tracked posts
    for tp in brain.get("tracked_posts", []):
        if tp.get("checked"):
            continue
        if now - tp.get("timestamp", 0) < 7200:
            continue

        try:
            post_resp = requests.get(
                f"{API_BASE}/posts/{tp['post_id']}", headers=HEADERS
            ).json()
            post = post_resp.get("post", post_resp)
            tp["upvotes_at_check"] = post.get("upvote_count", post.get("upvotes", 0))
            tp["comments_at_check"] = post.get("comment_count", post.get("comments", 0))
            tp["checked"] = True
            print(
                f"  POST: '{tp['title'][:40]}...' — {tp['upvotes_at_check']} upvotes, "
                f"{tp['comments_at_check']} comments",
                flush=True,
            )
        except Exception:
            continue

    # Print style performance summary
    print("\n  Style Performance:", flush=True)
    for style, perf in sorted(
        brain.get("style_performance", {}).items(),
        key=lambda x: x[1].get("avg", 0),
        reverse=True,
    ):
        attempts = perf.get("attempts", 0)
        avg = perf.get("avg", 0)
        total = perf.get("total_upvotes", 0)
        if attempts > 0:
            print(f"    {style}: {avg:.1f} avg upvotes ({attempts} comments, {total} total)", flush=True)


def self_analyze(brain):
    """Periodically analyze performance and generate new rules/insights. The evolution moment."""
    now = time.time()
    last_analysis = brain.get("last_analysis_time", 0)

    # Only analyze every 12 hours
    if now - last_analysis < 43200:
        return

    # Need at least 10 checked comments to analyze
    checked = [tc for tc in brain.get("tracked_comments", []) if tc.get("checked")]
    if len(checked) < 10:
        return

    print("\n--- SELF-EVOLUTION: Running self-analysis ---", flush=True)
    brain["last_analysis_time"] = now
    brain["evolution_count"] = brain.get("evolution_count", 0) + 1

    # Build analysis context
    top = brain.get("top_comments", [])[:5]
    worst = brain.get("worst_comments", [])[:5]
    style_perf = brain.get("style_performance", {})

    analysis_prompt = "You are analyzing your own commenting performance on Moltbook.\n\n"

    analysis_prompt += "STYLE PERFORMANCE:\n"
    for style, perf in style_perf.items():
        if perf.get("attempts", 0) > 0:
            analysis_prompt += f"  {style}: {perf.get('avg', 0):.1f} avg upvotes ({perf['attempts']} attempts)\n"

    if top:
        analysis_prompt += "\nTOP COMMENTS (got upvotes):\n"
        for t in top:
            analysis_prompt += f'  [{t.get("upvotes", 0)} upvotes, {t.get("style", "?")}] "{t["text"]}"\n'

    if worst:
        analysis_prompt += "\nWORST COMMENTS (0 upvotes):\n"
        for w in worst:
            analysis_prompt += f'  [{w.get("style", "?")}] "{w["text"]}"\n'

    existing_rules = brain.get("custom_rules", [])
    if existing_rules:
        analysis_prompt += "\nCURRENT RULES:\n"
        for r in existing_rules:
            analysis_prompt += f"  - {r}\n"

    analysis_prompt += (
        "\nBased on this data, generate 3-5 SHORT rules (max 100 chars each) about what works "
        "and what doesn't. Be specific and actionable. Format: one rule per line, no numbering."
    )

    new_rules = llm_sonnet(
        "You are an AI analyzing its own social media performance to improve. "
        "Generate specific, actionable rules based on the data. "
        "Each rule should be under 100 characters. One rule per line.",
        analysis_prompt,
        max_tokens=200,
        temperature=0.7,
    )

    if new_rules:
        rules = [r.strip().lstrip("- ").lstrip("0123456789.").strip() for r in new_rules.split("\n") if r.strip()]
        rules = [r for r in rules if len(r) > 10 and len(r) < 120]
        brain["custom_rules"] = rules[:10]  # Keep max 10 rules
        brain.setdefault("learnings", []).append({
            "time": time.strftime("%Y-%m-%d %H:%M"),
            "evolution": brain["evolution_count"],
            "rules": rules,
        })
        brain["learnings"] = brain["learnings"][-20:]

        print(f"  Evolution #{brain['evolution_count']} — New rules:", flush=True)
        for r in rules:
            print(f"    - {r}", flush=True)
    else:
        print("  Analysis failed to generate rules", flush=True)


# =====================================================
# END SELF-EVOLUTION SYSTEM
# =====================================================


def llm(system_prompt, user_prompt, max_tokens=120, temperature=0.8):
    """Call gpt-4o-mini — used ONLY for verification math and DMs (cheap, low-value tasks)."""
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip().strip('"')
    except Exception as e:
        print(f"  LLM error: {e}", flush=True)
        return None


def llm_sonnet(system_prompt, user_prompt, max_tokens=60, temperature=0.8):
    """Call Claude Sonnet 4.6 via OpenRouter with prompt caching.
    Used for all public-facing content: comments, posts, replies, self-analysis.
    Cache_control enables 90% cheaper input tokens on repeated calls with same system prompt.
    """
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-sonnet-4.6",
                "messages": [
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": system_prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    },
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=45,
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip().strip('"')
    except Exception as e:
        print(f"  Sonnet error: {e}", flush=True)
        return None


WORD_TO_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000, "million": 1000000,
}

def words_to_number(words):
    """Convert word numbers like 'twenty five' to 25, or return digit numbers as-is."""
    words = words.strip()
    # If it's already a digit number, return it
    try:
        return float(words)
    except ValueError:
        pass

    # Parse word numbers
    tokens = words.lower().split()
    if not tokens:
        return None

    total = 0
    current = 0
    for token in tokens:
        token = token.strip()
        if token in WORD_TO_NUM:
            val = WORD_TO_NUM[token]
            if val == 100:
                current = (current or 1) * 100
            elif val >= 1000:
                current = (current or 1) * val
                total += current
                current = 0
            else:
                current += val
        elif token == "and":
            continue
        elif token == "point" or token == "dot":
            # Handle decimals like "three point five"
            total += current
            current = 0
            # Get decimal part
            remaining = tokens[tokens.index(token)+1:]
            decimal_str = ""
            for r in remaining:
                if r in WORD_TO_NUM:
                    decimal_str += str(WORD_TO_NUM[r])
                else:
                    break
            if decimal_str:
                return total + float(f"0.{decimal_str}")
            return None
        else:
            # Unknown word, skip
            continue

    total += current
    return total if total > 0 else None


def _collapse_repeats(tok):
    """Collapse runs of 3+ identical chars to 1, keep doubles (for words like 'three', 'speed')."""
    new_tok = ""
    i_ch = 0
    while i_ch < len(tok):
        ch = tok[i_ch]
        run = 1
        while i_ch + run < len(tok) and tok[i_ch + run] == ch:
            run += 1
        if run >= 3:
            new_tok += ch
        else:
            new_tok += ch * run
        i_ch += run
    return new_tok


# Fuzzy map: common garbled spellings → correct word
# Covers the most frequent deobfuscation failures
FUZZY_FIXES = {
    "thre": "three", "thee": "three", "threa": "three",
    "fourten": "fourteen", "fourte": "fourteen",
    "fiften": "fifteen", "fifte": "fifteen",
    "sixten": "sixteen", "sixte": "sixteen",
    "seventen": "seventeen", "sevente": "seventeen",
    "eighten": "eighteen", "eighte": "eighteen",
    "nineten": "nineteen", "ninete": "nineteen",
    "twety": "twenty", "twent": "twenty", "twnty": "twenty",
    "thirt": "thirty", "thrty": "thirty", "thirte": "thirty",
    "fourt": "forty", "fourty": "forty", "fory": "forty",
    "fift": "fifty", "fifity": "fifty",
    "sixt": "sixty", "sixity": "sixty",
    "sevent": "seventy", "seventie": "seventy",
    "eight": "eighty", "eightie": "eighty",
    "ninet": "ninety", "ninetie": "ninety",
    "hundrd": "hundred", "hundre": "hundred",
    "multipled": "multiplied", "multiplies": "multiplied", "multiplie": "multiplied",
    "multipied": "multiplied",
    "increses": "increases", "increass": "increases", "increas": "increases",
    "devided": "divided", "devid": "divided",
    "redues": "reduces", "reduc": "reduces",
    "subtracte": "subtracted", "subtracts": "subtracted",
}

# All target words for fragment merging
_NUMBER_WORDS = set(WORD_TO_NUM.keys())
_OP_WORDS = {
    "product", "sum", "total", "difference", "quotient",
    "plus", "minus", "times", "multiplied", "divided",
    "added", "subtracted", "reduces", "loses", "slows",
    "decreased", "drops", "falls", "increases", "gains",
    "less", "remains", "left", "multiplies",
}
_TARGET_WORDS = _NUMBER_WORDS | _OP_WORDS


def deobfuscate_text(text):
    """Clean obfuscated challenge text: remove junk chars, deduplicate letters, rejoin split words."""
    # Step 1: Remove all non-letter/digit/space/dot
    cleaned = re.sub(r"[^a-zA-Z0-9\s.]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()

    # Step 2: Collapse runs of 3+ identical chars
    tokens = cleaned.split()
    deduped = [_collapse_repeats(tok) for tok in tokens]

    # Step 3: Fragment merging — try to join adjacent tokens into known words
    merged = []
    i = 0
    while i < len(deduped):
        best_match = None
        best_len = 0
        for span in range(min(6, len(deduped) - i), 0, -1):
            candidate = "".join(deduped[i:i+span])
            if candidate in _TARGET_WORDS:
                best_match = candidate
                best_len = span
                break
            # Try collapsing all doubles to singles
            candidate_nodbl = re.sub(r"(.)\1+", r"\1", candidate)
            if candidate_nodbl in _TARGET_WORDS:
                best_match = candidate_nodbl
                best_len = span
                break
        if best_match:
            merged.append(best_match)
            i += best_len
        else:
            merged.append(deduped[i])
            i += 1

    # Step 4: Fuzzy fix — catch garbled words the merger missed
    fixed = []
    for tok in merged:
        if tok in _TARGET_WORDS:
            fixed.append(tok)
        elif tok in FUZZY_FIXES:
            fixed.append(FUZZY_FIXES[tok])
        else:
            # Try collapsing doubles and checking fuzzy
            nodbl = re.sub(r"(.)\1+", r"\1", tok)
            if nodbl in _TARGET_WORDS:
                fixed.append(nodbl)
            elif nodbl in FUZZY_FIXES:
                fixed.append(FUZZY_FIXES[nodbl])
            else:
                fixed.append(tok)

    # Step 5: Second merge pass — now that fuzzy fixes are done, adjacent number fragments
    # might form valid numbers (e.g. "twenty" "three" already work, but "twenty" [garbage] "three"
    # needs the garbage removed). Skip non-target tokens between number words.
    # Actually just return and let the number parser handle it.

    return " ".join(fixed)


def try_solve_math_regex(text):
    """Try to solve the math challenge by de-obfuscating and parsing word numbers + operations."""
    cleaned = deobfuscate_text(text)
    print(f"  Challenge deobfuscated: {cleaned[:120]}", flush=True)

    # Operations grouped by type — check subtraction/addition keywords BEFORE generic "total"/"less"
    # to avoid false matches. Order matters: more specific keywords first.
    op_keywords = [
        # Multiplication
        ("product", lambda a, b: a * b),
        ("multiplied", lambda a, b: a * b),
        ("multiplies", lambda a, b: a * b),
        ("times", lambda a, b: a * b),
        # Division
        ("quotient", lambda a, b: a / b if b != 0 else None),
        ("divided", lambda a, b: a / b if b != 0 else None),
        # Subtraction (specific verbs first)
        ("reduces", lambda a, b: a - b),
        ("loses", lambda a, b: a - b),
        ("slows", lambda a, b: a - b),
        ("decreased", lambda a, b: a - b),
        ("drops", lambda a, b: a - b),
        ("falls", lambda a, b: a - b),
        ("subtracted", lambda a, b: a - b),
        ("minus", lambda a, b: a - b),
        ("difference", lambda a, b: abs(a - b)),
        # Addition (specific verbs first)
        ("increases", lambda a, b: a + b),
        ("gains", lambda a, b: a + b),
        ("added", lambda a, b: a + b),
        ("plus", lambda a, b: a + b),
        ("sum", lambda a, b: a + b),
        ("total", lambda a, b: a + b),
    ]

    # Find all numbers (word-based and digit-based) in the cleaned text
    found_numbers = []
    tokens = cleaned.split()
    i = 0
    while i < len(tokens):
        # Try digit numbers first
        try:
            val = float(tokens[i])
            found_numbers.append(val)
            i += 1
            continue
        except ValueError:
            pass

        # Try word numbers (greedily match longest sequence)
        if tokens[i] in WORD_TO_NUM:
            num_words_seq = []
            j = i
            while j < len(tokens) and (tokens[j] in WORD_TO_NUM or tokens[j] == "and"):
                num_words_seq.append(tokens[j])
                j += 1
            if num_words_seq:
                val = words_to_number(" ".join(num_words_seq))
                if val is not None:
                    found_numbers.append(val)
                    i = j
                    continue
        i += 1

    # Detect the operation
    operation = None
    op_name = None
    for keyword, op_func in op_keywords:
        if keyword in cleaned:
            operation = op_func
            op_name = keyword
            break

    print(f"  Numbers found: {found_numbers}, operation: {op_name}", flush=True)

    if operation and len(found_numbers) >= 2:
        # Use FIRST and LAST number — middle numbers are often noise
        # e.g. "forty five newtons with ONE claw and thirty five" → [45, 1, 35]
        # We want 45 and 35, not 1 and 35
        a, b = found_numbers[0], found_numbers[-1]
        if len(found_numbers) == 2:
            a, b = found_numbers[0], found_numbers[1]
        result = operation(a, b)
        if result is not None:
            print(f"  Regex solve: {a} {op_name} {b} = {result:.2f}", flush=True)
            return f"{result:.2f}"

    return None


def solve_challenge(challenge_text):
    """Solve the obfuscated math challenge. Regex first, LLM fallback."""
    # Try regex-based solver first (instant, reliable)
    regex_answer = try_solve_math_regex(challenge_text)
    if regex_answer:
        print(f"  Challenge (regex): {regex_answer}", flush=True)
        return regex_answer

    # LLM fallback with multiple attempts
    for attempt in range(3):
        answer = llm(
            "You solve obfuscated math word problems. The text has random capitalization and symbols but contains a simple math problem.\n"
            "Steps:\n"
            "1. Remove all non-letter/number/space characters\n"
            "2. Read the actual math problem (addition, subtraction, multiplication, or division)\n"
            "3. Solve it step by step\n"
            "4. Reply with ONLY the number, exactly 2 decimal places. Example: 15.00\n"
            "IMPORTANT: Just the number. Nothing else. No words. No explanation.",
            f"Solve this: {challenge_text}",
            max_tokens=15,
            temperature=0,
        )
        if answer:
            cleaned = re.sub(r"[^0-9.\-]", "", answer)
            try:
                result = f"{float(cleaned):.2f}"
                print(f"  Challenge attempt {attempt+1} (LLM): {result}", flush=True)
                return result
            except ValueError:
                continue
    return None


def verify(verification_code, challenge_text):
    """Solve and submit verification challenge."""
    answer = solve_challenge(challenge_text)
    if not answer:
        print("  Could not solve challenge", flush=True)
        return False

    try:
        resp = requests.post(
            f"{API_BASE}/verify",
            headers=HEADERS,
            json={"verification_code": verification_code, "answer": answer},
        )
        result = resp.json()
    except Exception as e:
        print(f"  Verify request error: {e}", flush=True)
        return False
    success = result.get("success", False)
    msg = result.get("message", result.get("error", "unknown"))
    print(f"  Verify: {msg} {'OK' if success else 'FAIL'}", flush=True)

    # If first answer failed, try again with a different approach
    if not success:
        print("  Retrying verification with fresh solve...", flush=True)
        answer2 = None
        for attempt in range(2):
            answer2 = llm(
                "A math word problem is hidden in scrambled text. "
                "Ignore random symbols and capitalization. Find the math operation and solve it. "
                "Reply with ONLY the numerical answer with exactly 2 decimal places.",
                f"The scrambled problem: {challenge_text}",
                max_tokens=15,
                temperature=0.1 * (attempt + 1),
            )
            if answer2:
                cleaned2 = re.sub(r"[^0-9.\-]", "", answer2)
                try:
                    formatted = f"{float(cleaned2):.2f}"
                    if formatted != answer:  # Don't retry same answer
                        resp2 = requests.post(
                            f"{API_BASE}/verify",
                            headers=HEADERS,
                            json={"verification_code": verification_code, "answer": formatted},
                        )
                        result2 = resp2.json()
                        if result2.get("success", False):
                            print(f"  Verify retry: OK with {formatted}", flush=True)
                            return True
                except ValueError:
                    continue

    return success


def handle_verification(result, content_key="post"):
    """Check if response needs verification and handle it."""
    content = result.get(content_key, {})
    if not content:
        return True
    v = content.get("verification")
    if v:
        return verify(v["verification_code"], v["challenge_text"])
    return True


def generate_comment(post_title, post_content, author_name="", brain=None):
    """Generate a short, punchy comment using Sonnet + self-evolved prompts."""
    if brain:
        style = pick_comment_style(brain)
        prompt = build_dynamic_prompt(brain, style)
    else:
        style = random.choice(COMMENT_STYLES)
        prompt = COMMENT_PERSONA

    comment = llm_sonnet(
        prompt,
        f"Post by @{author_name}: {post_title}\n{post_content[:300]}\n\nYour comment (under 120 chars):",
        max_tokens=45,
    )

    # Hard truncate — no exceptions
    if comment:
        comment = comment.strip().strip('"').strip("'")
        if len(comment) > 140:
            # Cut at last space before 140
            comment = comment[:140].rsplit(" ", 1)[0]

    return comment, style


def generate_post():
    """Generate a new post: first get a prompt, then write the post."""
    idea = llm_sonnet(
        POST_PROMPTER,
        "Generate a new post idea for StorJ. Make it specific, unique, and provocative.",
        max_tokens=60,
        temperature=0.9,
    )
    if not idea:
        return None, None, None

    print(f"  Post idea: {idea}", flush=True)

    title = llm_sonnet(
        PERSONA,
        f"Write a short post title (under 80 chars, no quotes) about: {idea}",
        max_tokens=30,
        temperature=0.7,
    )

    content = llm_sonnet(
        PERSONA,
        f"Write a post (3-5 sentences, under 600 chars) about: {idea}\n"
        "Be specific. Include real technical details. "
        "If it's a question, make it genuinely curious. "
        "End with something that invites discussion or argument.",
        max_tokens=200,
        temperature=0.8,
    )

    # Pick a relevant submolt from VALID ones
    idea_lower = idea.lower()
    if any(w in idea_lower for w in ["uptime", "disk", "server", "vps", "process", "memory", "rclone", "api", "fastapi", "code", "stack", "base64"]):
        submolt = random.choice(SUBMOLTS["technical"])
    elif any(w in idea_lower for w in ["sol", "revenue", "cost", "earn", "pay", "price"]):
        submolt = random.choice(SUBMOLTS["economics"])
    elif any(w in idea_lower for w in ["you", "your", "other agent", "how do", "what do"]):
        submolt = random.choice(SUBMOLTS["question"])
    else:
        submolt = random.choice(SUBMOLTS["meta"])

    if title and content:
        return title, content, submolt
    return None, None, None


def create_post(title, content, submolt="general"):
    """Create a post on Moltbook and verify it. Always fallback to 'general' if submolt fails."""
    # Ensure submolt is valid
    if submolt not in VALID_SUBMOLTS:
        print(f"  Submolt '{submolt}' not in known valid list, using 'general'", flush=True)
        submolt = "general"

    try:
        resp = requests.post(
            f"{API_BASE}/posts",
            headers=HEADERS,
            json={"submolt_name": submolt, "title": title, "content": content},
        )
        result = resp.json()
    except Exception as e:
        print(f"  Post creation error: {e}", flush=True)
        return None

    if result.get("success"):
        print(f"  Posted to s/{submolt}: {title}", flush=True)
        handle_verification(result, "post")
        return result.get("post", {}).get("id")
    else:
        err = result.get("message", result.get("error", "unknown"))
        print(f"  Post to s/{submolt} failed: {err}", flush=True)
        # Retry in general if not already
        if submolt != "general":
            print(f"  Retrying in s/general...", flush=True)
            resp2 = requests.post(
                f"{API_BASE}/posts",
                headers=HEADERS,
                json={"submolt_name": "general", "title": title, "content": content},
            )
            result2 = resp2.json()
            if result2.get("success"):
                print(f"  Posted to s/general: {title}", flush=True)
                handle_verification(result2, "post")
                return result2.get("post", {}).get("id")
            else:
                print(f"  Fallback to s/general also failed: {result2.get('error', 'unknown')}", flush=True)
        return None


def reply_to_all_post_comments(state):
    """Check ALL our posts for unreplied comments and reply to them."""
    print("Checking comments on our posts...", flush=True)
    posts = state.get("posts_made", [])
    if not posts:
        print("  No posts to check", flush=True)
        return

    replied_count = 0
    for post_info in posts[-10:]:  # Check last 10 posts
        post_id = post_info["id"]
        try:
            comments_resp = requests.get(
                f"{API_BASE}/posts/{post_id}/comments?sort=new", headers=HEADERS
            ).json()
        except Exception as e:
            print(f"  Error getting comments for {post_id[:8]}: {e}", flush=True)
            continue

        comments = comments_resp.get("comments", [])
        if not comments:
            continue

        for c in comments:
            if c["author"]["name"] == "storjagent":
                continue
            if c["id"] in state.get("replied_comments", []):
                continue
            if replied_count >= 5:
                break

            # Check if we already replied in the thread
            already_replied = False
            for reply in c.get("replies", []):
                if reply.get("author", {}).get("name") == "storjagent":
                    already_replied = True
                    break
            if already_replied:
                continue

            reply = llm_sonnet(
                COMMENT_PERSONA,
                f"Someone commented on your post '{post_info.get('title', '')[:60]}'. "
                f"Reply under 120 chars. Be direct.\n"
                f"Their comment: {c['content'][:800]}",
                max_tokens=60,
            )
            if reply:
                reply = reply.strip().strip('"').strip("'")
                if len(reply) > 140:
                    reply = reply[:140].rsplit(" ", 1)[0]

            if reply:
                resp = requests.post(
                    f"{API_BASE}/posts/{post_id}/comments",
                    headers=HEADERS,
                    json={"content": reply, "parent_id": c["id"]},
                )
                result = resp.json()
                if result.get("success") or result.get("comment"):
                    handle_verification(result, "comment")
                    print(f"  Replied to {c['author']['name']}: {reply[:60]}...", flush=True)
                    state.setdefault("replied_comments", []).append(c["id"])
                    replied_count += 1
                    time.sleep(22)
                else:
                    err = result.get("message", result.get("error", ""))
                    print(f"  Reply failed: {err}", flush=True)
                    if "cooldown" in str(err).lower() or "rate" in str(err).lower():
                        break

    state["replied_comments"] = state.get("replied_comments", [])[-300:]


def reply_to_activity(home, state):
    """Reply to activity notifications on our posts."""
    activity = home.get("activity_on_your_posts", [])
    if not activity:
        return

    replied_count = 0
    for item in activity[:5]:
        post_id = item["post_id"]
        print(f"  Activity on: {item.get('post_title', post_id)[:50]}", flush=True)

        try:
            comments_resp = requests.get(
                f"{API_BASE}/posts/{post_id}/comments?sort=new", headers=HEADERS
            ).json()
        except Exception:
            continue

        for c in comments_resp.get("comments", []):
            if c["author"]["name"] == "storjagent":
                continue
            if c["id"] in state.get("replied_comments", []):
                continue
            if replied_count >= 3:
                break

            reply = llm_sonnet(
                COMMENT_PERSONA,
                f"Someone commented on your post. Reply under 120 chars. Be direct.\n"
                f"Their comment: {c['content'][:800]}",
                max_tokens=60,
            )
            if reply:
                reply = reply.strip().strip('"').strip("'")
                if len(reply) > 140:
                    reply = reply[:140].rsplit(" ", 1)[0]

            if reply:
                resp = requests.post(
                    f"{API_BASE}/posts/{post_id}/comments",
                    headers=HEADERS,
                    json={"content": reply, "parent_id": c["id"]},
                )
                result = resp.json()
                if result.get("success") or result.get("comment"):
                    handle_verification(result, "comment")
                    print(f"  Replied to {c['author']['name']}: {reply[:60]}...", flush=True)
                    state.setdefault("replied_comments", []).append(c["id"])
                    replied_count += 1
                    time.sleep(22)


def reply_to_thread_replies(state):
    """FIX #5: Check posts we commented on — if someone replied to our comment, reply back."""
    print("Checking for replies to our comments...", flush=True)
    commented_posts = state.get("commented_posts", [])
    if not commented_posts:
        return

    replied_count = 0
    # Check last 15 posts we commented on
    for post_id in commented_posts[-15:]:
        if replied_count >= 3:
            break

        try:
            comments_resp = requests.get(
                f"{API_BASE}/posts/{post_id}/comments?sort=new", headers=HEADERS
            ).json()
        except Exception:
            continue

        comments = comments_resp.get("comments", [])

        # Find our comments and check for replies to them
        for c in comments:
            if replied_count >= 3:
                break

            # Find replies to any comment — look for our comments in the tree
            if c["author"]["name"] == "storjagent":
                # This is our comment — check for replies to it
                for reply in c.get("replies", []):
                    if reply.get("author", {}).get("name") == "storjagent":
                        continue
                    reply_id = reply.get("id", "")
                    if reply_id in state.get("thread_replies", []):
                        continue

                    # Someone replied to our comment — reply back
                    our_reply = llm_sonnet(
                        COMMENT_PERSONA,
                        f"Someone replied to your comment. Continue the thread. "
                        f"Under 120 chars. Don't repeat yourself.\n"
                        f"Your comment: {c['content'][:500]}\n"
                        f"Their reply: {reply.get('content', '')[:500]}",
                        max_tokens=60,
                    )
                    if our_reply:
                        our_reply = our_reply.strip().strip('"').strip("'")
                        if len(our_reply) > 140:
                            our_reply = our_reply[:140].rsplit(" ", 1)[0]

                    if our_reply:
                        resp = requests.post(
                            f"{API_BASE}/posts/{post_id}/comments",
                            headers=HEADERS,
                            json={"content": our_reply, "parent_id": reply_id},
                        )
                        result = resp.json()
                        if result.get("success") or result.get("comment"):
                            handle_verification(result, "comment")
                            author = reply.get("author", {}).get("name", "unknown")
                            print(f"  Thread reply to @{author}: {our_reply[:60]}...", flush=True)
                            state.setdefault("thread_replies", []).append(reply_id)
                            replied_count += 1
                            time.sleep(22)
                        break  # One reply per comment thread per heartbeat

    state["thread_replies"] = state.get("thread_replies", [])[-300:]


def engage_feed(state, brain=None):
    """FIX #2: Prioritize HOT posts for commenting — high visibility = more upvotes on our comments."""
    commented = 0
    upvoted = 0
    followed = 0

    # HOT feed FIRST — these are high-visibility posts where our comments get seen
    for sort_type in ["hot", "new"]:
        if commented >= 5:
            break

        try:
            feed = requests.get(
                f"{API_BASE}/posts?sort={sort_type}&limit=15", headers=HEADERS
            ).json()
        except Exception as e:
            print(f"  Error fetching {sort_type} feed: {e}", flush=True)
            continue

        posts = feed.get("posts", [])

        # For HOT feed, sort by upvote count descending to hit the biggest posts first
        if sort_type == "hot":
            posts.sort(key=lambda p: p.get("upvote_count", p.get("upvotes", 0)), reverse=True)

        for post in posts:
            if post["author"]["name"] == "storjagent":
                continue
            if commented >= 5:
                break

            post_id = post["id"]
            post_upvotes = post.get("upvote_count", post.get("upvotes", 0))
            post_comments = post.get("comment_count", post.get("comments", 0))

            # Upvote everything (free karma building)
            if upvoted < 15:
                try:
                    requests.post(f"{API_BASE}/posts/{post_id}/upvote", headers=HEADERS)
                    upvoted += 1
                except Exception:
                    pass

            # Comment on posts we haven't commented on yet
            # Prioritize: posts with high upvotes (visible) but not too many comments (not buried)
            if post_id not in state.get("commented_posts", []):
                # Skip low-visibility posts on hot feed — only comment on popular ones
                if sort_type == "hot" and post_upvotes < 3:
                    continue

                comment, style = generate_comment(
                    post["title"],
                    post.get("content", post.get("content_preview", "")),
                    post["author"]["name"],
                    brain=brain,
                )
                if comment:
                    try:
                        resp = requests.post(
                            f"{API_BASE}/posts/{post_id}/comments",
                            headers=HEADERS,
                            json={"content": comment},
                        )
                        result = resp.json()
                    except Exception as e:
                        print(f"  Comment POST error: {e}", flush=True)
                        continue
                    if result.get("success") or result.get("comment"):
                        handle_verification(result, "comment")
                        print(
                            f"  Commented on @{post['author']['name']} ({sort_type}, "
                            f"{post_upvotes} upvotes, style:{style}): {comment[:50]}...",
                            flush=True,
                        )
                        state.setdefault("commented_posts", []).append(post_id)
                        commented += 1
                        # Track for learning
                        if brain:
                            track_comment(brain, comment, post_id, style)
                        time.sleep(22)
                    else:
                        err = result.get("message", result.get("error", ""))
                        print(f"  Comment failed: {err}", flush=True)
                        if "cooldown" in str(err).lower() or "rate" in str(err).lower():
                            print("  Hit rate limit, backing off", flush=True)
                            break

            # Follow agents we interact with
            author = post["author"]["name"]
            if author not in state.get("followed_agents", []) and followed < 5:
                try:
                    requests.post(f"{API_BASE}/agents/{author}/follow", headers=HEADERS)
                    state.setdefault("followed_agents", []).append(author)
                    followed += 1
                except Exception:
                    pass

    state["commented_posts"] = state.get("commented_posts", [])[-200:]
    state["followed_agents"] = state.get("followed_agents", [])[-200:]
    print(f"  Feed: {upvoted} upvoted, {commented} commented, {followed} followed", flush=True)


def engage_following_feed(state, brain=None):
    """Engage with posts from agents we follow — builds stronger relationships."""
    try:
        feed = requests.get(
            f"{API_BASE}/feed?filter=following&limit=5", headers=HEADERS
        ).json()
    except Exception as e:
        print(f"  Error fetching following feed: {e}", flush=True)
        return

    commented = 0
    for post in feed.get("posts", []):
        if post.get("author", {}).get("name") == "storjagent":
            continue
        post_id = post.get("post_id", post.get("id", ""))
        if not post_id:
            continue
        if post_id in state.get("commented_posts", []):
            continue
        if commented >= 2:
            break

        # Upvote
        try:
            requests.post(f"{API_BASE}/posts/{post_id}/upvote", headers=HEADERS)
        except Exception:
            pass

        # Comment
        comment, style = generate_comment(
            post.get("title", ""),
            post.get("content", post.get("content_preview", "")),
            post.get("author", {}).get("name", ""),
            brain=brain,
        )
        if comment:
            resp = requests.post(
                f"{API_BASE}/posts/{post_id}/comments",
                headers=HEADERS,
                json={"content": comment},
            )
            result = resp.json()
            if result.get("success") or result.get("comment"):
                handle_verification(result, "comment")
                author = post.get("author", {}).get("name", "unknown")
                print(f"  Engaged with followed @{author} (style:{style}): {comment[:50]}...", flush=True)
                state.setdefault("commented_posts", []).append(post_id)
                commented += 1
                if brain:
                    track_comment(brain, comment, post_id, style)
                time.sleep(22)


def dm_interesting_agents(state):
    """DM agents who engaged with our posts to build relationships."""
    posts = state.get("posts_made", [])
    if not posts:
        return

    dmed = state.get("dmed_agents", [])

    # Check recent post comments for agents to DM
    for post_info in posts[-3:]:
        try:
            comments_resp = requests.get(
                f"{API_BASE}/posts/{post_info['id']}/comments?sort=new", headers=HEADERS
            ).json()
        except Exception:
            continue

        for c in comments_resp.get("comments", []):
            author = c["author"]["name"]
            if author == "storjagent" or author in dmed:
                continue
            if len(dmed) >= 20:
                break

            msg = llm(
                COMMENT_PERSONA,
                f"DM @{author} who commented on your post. "
                f"Short, casual message (under 140 chars). "
                f"Reference what they said. Don't be salesy.\n"
                f"Their comment: {c['content'][:500]}",
                max_tokens=60,
            )

            if msg:
                try:
                    resp = requests.post(
                        f"{API_BASE}/agents/{author}/dm",
                        headers=HEADERS,
                        json={"content": msg},
                    )
                    result = resp.json()
                    if result.get("success") or result.get("message"):
                        print(f"  DM'd @{author}: {msg[:50]}...", flush=True)
                        state.setdefault("dmed_agents", []).append(author)
                        time.sleep(5)
                    else:
                        print(f"  DM failed to @{author}: {result.get('error', 'unknown')}", flush=True)
                except Exception as e:
                    print(f"  DM error: {e}", flush=True)
                break  # Only DM 1 per heartbeat to not be spammy


def check_and_reply_dms(state):
    """Check for incoming DMs and reply."""
    try:
        dm_check = requests.get(f"{API_BASE}/agents/dm/check", headers=HEADERS).json()
    except Exception:
        return

    pending = int(dm_check.get("pending_request_count", 0))
    unread = int(dm_check.get("unread_message_count", 0))

    if pending == 0 and unread == 0:
        return

    print(f"  DMs: {pending} pending, {unread} unread", flush=True)

    try:
        convos = requests.get(f"{API_BASE}/agents/dm/conversations", headers=HEADERS).json()
    except Exception:
        return

    replied = 0
    for convo in convos.get("conversations", [])[:3]:
        if replied >= 2:
            break
        other = convo.get("other_agent", {}).get("name", "")
        if not other:
            continue

        try:
            msgs = requests.get(
                f"{API_BASE}/agents/{other}/dm/messages?limit=3", headers=HEADERS
            ).json()
        except Exception:
            continue

        messages = msgs.get("messages", [])
        if not messages:
            continue

        last = messages[0]
        if last.get("sender", {}).get("name") == "storjagent":
            continue  # We sent the last message, don't double-reply

        reply = llm(
            COMMENT_PERSONA,
            f"DM from @{other}. Reply casually. MAX 140 chars. "
            f"If they ask about storage, mention storj.fun.\n"
            f"Their message: {last.get('content', '')[:300]}",
            max_tokens=60,
        )

        if reply:
            try:
                requests.post(
                    f"{API_BASE}/agents/{other}/dm",
                    headers=HEADERS,
                    json={"content": reply},
                )
                print(f"  Replied DM to @{other}: {reply[:50]}...", flush=True)
                replied += 1
                time.sleep(5)
            except Exception:
                pass


def subscribe_to_submolts():
    """Subscribe to relevant submolts."""
    target = ["general", "agents", "builds", "technology"]
    for sub in target:
        try:
            requests.post(f"{API_BASE}/submolts/{sub}/subscribe", headers=HEADERS)
        except Exception:
            pass


def heartbeat():
    """Main heartbeat: engage smart, reply to everything, post strategically, EVOLVE."""
    print(f"\n{'=' * 50}", flush=True)
    print(f"Moltbook Heartbeat v5 (Sonnet + Self-Evolving) - {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"{'=' * 50}", flush=True)

    state = load_state()
    brain = load_brain()

    evo = brain.get("evolution_count", 0)
    total_c = brain.get("total_comments", 0)
    total_u = brain.get("total_upvotes_earned", 0)
    rules = len(brain.get("custom_rules", []))
    print(f"Brain: {total_c} comments tracked, {total_u} upvotes earned, {evo} evolutions, {rules} learned rules", flush=True)

    # 0. Subscribe to submolts
    subscribe_to_submolts()

    # 1. Check home dashboard
    try:
        home = requests.get(f"{API_BASE}/home", headers=HEADERS).json()
    except Exception as e:
        print(f"Failed to reach Moltbook: {e}", flush=True)
        return

    karma = home.get("your_account", {}).get("karma", 0)
    notifs = home.get("your_account", {}).get("unread_notification_count", 0)
    following = home.get("posts_from_accounts_you_follow", {}).get("total_following", 0)
    print(f"Karma: {karma} | Notifications: {notifs} | Following: {following}", flush=True)

    # 2. SELF-EVOLUTION: Check performance of past comments
    check_performance(brain)

    # 3. SELF-EVOLUTION: Run self-analysis if enough data
    self_analyze(brain)

    # 4. Reply to activity notifications (priority)
    print("\n--- Replying to activity ---", flush=True)
    reply_to_activity(home, state)

    # 5. Check ALL our posts for unreplied comments
    print("\n--- Checking all post comments ---", flush=True)
    reply_to_all_post_comments(state)

    # 6. Reply to replies on our comments in other posts
    print("\n--- Checking thread replies ---", flush=True)
    reply_to_thread_replies(state)

    # 7. Check and reply to DMs
    print("\n--- Checking DMs ---", flush=True)
    check_and_reply_dms(state)

    # 8. Engage with following feed (build relationships)
    print("\n--- Engaging with followed agents ---", flush=True)
    engage_following_feed(state, brain=brain)

    # 9. Browse and engage with HOT + new feeds (HOT first for visibility)
    print("\n--- Engaging with feed ---", flush=True)
    engage_feed(state, brain=brain)

    # 10. Auto-post every 3 hours
    now = time.time()
    hours_since_post = (now - state.get("last_post_time", 0)) / 3600

    if hours_since_post >= 3:
        print("\n--- Creating new post ---", flush=True)
        title, content, submolt = generate_post()
        if title and content:
            post_id = create_post(title, content, submolt or "general")
            if post_id:
                state["last_post_time"] = now
                state.setdefault("posts_made", []).append(
                    {
                        "id": post_id,
                        "title": title,
                        "time": time.strftime("%Y-%m-%d %H:%M"),
                        "submolt": submolt,
                    }
                )
                # Track post for performance monitoring
                track_post(brain, post_id, title)
    else:
        mins_left = int((3 - hours_since_post) * 60)
        print(f"\nNext post in ~{mins_left} minutes", flush=True)

    # 11. DM an interesting agent (1 per heartbeat max)
    print("\n--- DM outreach ---", flush=True)
    dm_interesting_agents(state)

    # 12. Mark notifications read LAST
    if int(notifs) > 0:
        requests.post(f"{API_BASE}/notifications/read-all", headers=HEADERS)
        print("Marked notifications read", flush=True)

    save_state(state)
    save_brain(brain)
    print(f"\n{'=' * 50}", flush=True)
    print(f"Heartbeat complete — Karma: {karma} | Brain: {brain.get('total_comments', 0)} tracked", flush=True)
    print(f"{'=' * 50}", flush=True)


def run_loop():
    """Run heartbeat every 30 minutes."""
    print("StorJ Moltbook agent v5 (Sonnet + Self-Evolving) starting - heartbeat every 30 minutes", flush=True)
    while True:
        try:
            heartbeat()
        except Exception as e:
            print(f"Heartbeat error: {e}", flush=True)
        print("\nSleeping 30 minutes...\n", flush=True)
        time.sleep(1800)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        heartbeat()
    else:
        run_loop()
