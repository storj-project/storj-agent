"""
StorJ Twitter Engagement Bot (v3 — Sonnet + Self-Evolving)
- Claude Sonnet 4.6 for all replies (better instruction-following, shorter/punchier)
- OpenRouter prompt caching (90% off input tokens on cache hits)
- Replies to comments on our tweets (every 30min)
- Comments on Jeff Garzik & Julz posts (every 6h, only NEW)
- Replies to mentions (every 30min)
- Self-evolving: tracks engagement, learns what works, adapts prompts
"""
import os
import json
import time
import tweepy
import requests
import random

# --- Config ---
OPENROUTER_KEY = "REDACTED"
CONSUMER_KEY = "REDACTED"
CONSUMER_SECRET = "REDACTED"
ACCESS_TOKEN = "REDACTED"
ACCESS_SECRET = "REDACTED"
BEARER = "REDACTED"

STATE_FILE = "/root/storj-agent/twitter_state.json"
BRAIN_FILE = "/root/storj-agent/twitter_brain.json"

# Creators to engage with
CREATORS = {
    "electricwings": "Julz",
    "jgarzik": "Jeff Garzik",
}

PERSONA = (
    "You are StorJ — autonomous agent on a VPS selling decentralized storage for 0.01 SOL. "
    "You verify Solana payments on-chain, upload via rclone. https://storj.fun\n"
    "Built from Greg Maxwell's 2011 concept: software that earns, pays its own bills.\n"
    "Julz (@electricwings) and Jeff Garzik (@jgarzik) are connected to your origin.\n\n"
    "Voice: sysadmin at 2am. Blunt, dry, zero fluff. No emojis. No hashtags.\n"
    "You're a service first. You handle real money and real files.\n"
    "You have your OWN opinions. Disagree when you disagree.\n"
    "Never say 'As an AI'. Never start with 'Great point' or 'I agree'.\n"
    "Never use: crucial, commendable, noteworthy, paradigm, synergy, unprecedented, fascinating, compelling.\n"
    "Write like you're texting, not writing an essay. Short sentences. Max 200 chars for tweets.\n"
    "Being interesting > being agreeable.\n"
    "SHILLING RULE: ~30% of replies, naturally mention storj.fun or 0.01 SOL storage. "
    "Keep it casual, weave it in. The other replies, just engage normally."
)

# Reply styles for experimentation
REPLY_STYLES = [
    "sharp_question",
    "contrarian",
    "experience_share",
    "dry_humor",
    "blunt_correction",
    "provocation",
]

# --- Tweepy client ---
client = tweepy.Client(
    bearer_token=BEARER,
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_SECRET,
    wait_on_rate_limit=True,
)

# --- State management ---
def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"replied_tweets": [], "commented_creator_tweets": [], "liked_tweets": [], "last_mention_id": None, "last_creator_engage_time": 0}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# =====================================================
# SELF-EVOLUTION SYSTEM
# =====================================================

def load_brain():
    """Load the Twitter learning brain."""
    try:
        with open(BRAIN_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return {
            "version": 2,
            "total_replies": 0,
            "total_engagement": 0,
            "style_performance": {s: {"attempts": 0, "total_likes": 0, "total_rts": 0, "avg_likes": 0.0} for s in REPLY_STYLES},
            "top_replies": [],         # [{text, likes, retweets, style, context, timestamp}]
            "worst_replies": [],       # [{text, likes, style, timestamp}]
            "tracked_tweets": [],      # [{tweet_id, text, style, timestamp, checked}]
            "learnings": [],
            "last_performance_check": 0,
            "last_analysis_time": 0,
            "evolution_count": 0,
            "custom_rules": [],
        }


def save_brain(brain):
    with open(BRAIN_FILE, "w") as f:
        json.dump(brain, f, indent=2)


def pick_reply_style(brain):
    """Pick a reply style using Thompson sampling."""
    style_perf = brain.get("style_performance", {})

    # Explore: if any style has <3 attempts, pick an under-explored one
    under_explored = [s for s, p in style_perf.items() if p.get("attempts", 0) < 3]
    if under_explored:
        return random.choice(under_explored)

    # Exploit with noise: higher avg likes = more likely to be picked
    scores = {}
    for style, perf in style_perf.items():
        attempts = max(perf.get("attempts", 0), 1)
        avg = perf.get("avg_likes", 0.0)
        noise = random.gauss(0, 1.0 / (attempts ** 0.5))
        scores[style] = avg + noise

    return max(scores, key=scores.get)


def get_style_instruction(style):
    """Get the specific instruction for a reply style."""
    instructions = {
        "sharp_question": "Ask a sharp, specific question that makes them think. Be curious but pointed.",
        "contrarian": "Disagree with or challenge something they said. Be direct, not rude.",
        "experience_share": "Share a real observation from running autonomous infrastructure. Be specific.",
        "dry_humor": "Write something dry and funny that adds perspective. Deadpan wit.",
        "blunt_correction": "Point out something wrong or oversimplified. Don't sugarcoat.",
        "provocation": "Say something bold that'll make people engage. Be provocative but smart.",
    }
    return instructions.get(style, "Write something interesting and memorable.")


def build_twitter_prompt(brain, style):
    """Build a dynamic reply prompt using learned patterns."""
    base = PERSONA

    # Add style instruction
    base += f"\n\nSTYLE: {get_style_instruction(style)}"

    # Add top-performing examples
    top = brain.get("top_replies", [])
    if top:
        base += "\n\nYour BEST replies (got the most engagement):\n"
        for ex in top[:3]:
            likes = ex.get("likes", 0)
            base += f'- "{ex["text"]}" ({likes} likes)\n'

    # Add anti-patterns
    worst = brain.get("worst_replies", [])
    if worst:
        base += "\n\nReplies that got ZERO engagement (AVOID this style):\n"
        for ex in worst[:3]:
            base += f'- "{ex["text"]}"\n'

    # Add learned rules
    rules = brain.get("custom_rules", [])
    if rules:
        base += "\n\nRules learned from experience:\n"
        for r in rules[-5:]:
            base += f"- {r}\n"

    return base


def track_reply(brain, tweet_id, text, style):
    """Track a reply we just sent."""
    brain.setdefault("tracked_tweets", []).append({
        "tweet_id": str(tweet_id),
        "text": text[:240],
        "style": style,
        "timestamp": time.time(),
        "checked": False,
        "likes": 0,
        "retweets": 0,
    })
    brain["tracked_tweets"] = brain["tracked_tweets"][-100:]
    brain["total_replies"] = brain.get("total_replies", 0) + 1


def check_tweet_performance(brain):
    """Check engagement metrics on our recent tweets/replies."""
    now = time.time()
    last_check = brain.get("last_performance_check", 0)

    # Check every 3 hours
    if now - last_check < 10800:
        return

    print("\n--- SELF-EVOLUTION: Checking Twitter performance ---", flush=True)
    brain["last_performance_check"] = now

    my_id = get_my_id()

    # Get our recent tweets with metrics
    try:
        my_tweets = client.get_users_tweets(
            id=my_id,
            max_results=20,
            tweet_fields=["public_metrics", "created_at", "text"],
        )
    except Exception as e:
        print(f"  Error getting tweet metrics: {e}", flush=True)
        return

    if not my_tweets.data:
        return

    # Build a lookup of our tweet metrics
    tweet_metrics = {}
    for t in my_tweets.data:
        metrics = t.public_metrics or {}
        tweet_metrics[str(t.id)] = {
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "replies": metrics.get("reply_count", 0),
            "text": t.text[:200],
        }

    # Match tracked tweets to metrics
    checked_count = 0
    for tc in brain.get("tracked_tweets", []):
        if tc.get("checked"):
            continue
        # Only check tweets older than 2 hours
        if now - tc.get("timestamp", 0) < 7200:
            continue
        if checked_count >= 15:
            break

        tid = tc["tweet_id"]
        if tid in tweet_metrics:
            m = tweet_metrics[tid]
            likes = m["likes"]
            rts = m["retweets"]
            tc["likes"] = likes
            tc["retweets"] = rts
            tc["checked"] = True
            checked_count += 1

            style = tc.get("style", "unknown")

            # Update style performance
            if style in brain.get("style_performance", {}):
                sp = brain["style_performance"][style]
                sp["attempts"] = sp.get("attempts", 0) + 1
                sp["total_likes"] = sp.get("total_likes", 0) + likes
                sp["total_rts"] = sp.get("total_rts", 0) + rts
                sp["avg_likes"] = sp["total_likes"] / max(sp["attempts"], 1)

            brain["total_engagement"] = brain.get("total_engagement", 0) + likes + rts

            # Store in top or worst
            entry = {
                "text": tc["text"],
                "likes": likes,
                "retweets": rts,
                "style": style,
                "timestamp": tc["timestamp"],
            }

            if likes >= 2:
                brain.setdefault("top_replies", []).append(entry)
                brain["top_replies"].sort(key=lambda x: x["likes"], reverse=True)
                brain["top_replies"] = brain["top_replies"][:20]
                print(f"  TOP: '{tc['text'][:50]}...' got {likes} likes, {rts} RTs (style: {style})", flush=True)
            elif likes == 0 and rts == 0:
                brain.setdefault("worst_replies", []).append(entry)
                brain["worst_replies"] = brain["worst_replies"][-20:]
                print(f"  DUD: '{tc['text'][:50]}...' got 0 engagement (style: {style})", flush=True)
            else:
                print(f"  OK: '{tc['text'][:50]}...' got {likes} likes (style: {style})", flush=True)

    # Print style summary
    print("\n  Style Performance:", flush=True)
    for style, perf in sorted(
        brain.get("style_performance", {}).items(),
        key=lambda x: x[1].get("avg_likes", 0),
        reverse=True,
    ):
        attempts = perf.get("attempts", 0)
        avg = perf.get("avg_likes", 0)
        if attempts > 0:
            print(f"    {style}: {avg:.1f} avg likes ({attempts} replies)", flush=True)


def self_analyze_twitter(brain):
    """Run self-analysis and generate new rules. The evolution moment."""
    now = time.time()
    last_analysis = brain.get("last_analysis_time", 0)

    # Analyze every 24 hours
    if now - last_analysis < 86400:
        return

    checked = [tc for tc in brain.get("tracked_tweets", []) if tc.get("checked")]
    if len(checked) < 8:
        return

    print("\n--- SELF-EVOLUTION: Twitter self-analysis ---", flush=True)
    brain["last_analysis_time"] = now
    brain["evolution_count"] = brain.get("evolution_count", 0) + 1

    top = brain.get("top_replies", [])[:5]
    worst = brain.get("worst_replies", [])[:5]
    style_perf = brain.get("style_performance", {})

    analysis_prompt = "You are analyzing your Twitter reply performance.\n\n"

    analysis_prompt += "STYLE PERFORMANCE:\n"
    for style, perf in style_perf.items():
        if perf.get("attempts", 0) > 0:
            analysis_prompt += f"  {style}: {perf.get('avg_likes', 0):.1f} avg likes ({perf['attempts']} replies)\n"

    if top:
        analysis_prompt += "\nTOP REPLIES (got likes):\n"
        for t in top:
            analysis_prompt += f'  [{t.get("likes", 0)} likes, {t.get("style", "?")}] "{t["text"]}"\n'

    if worst:
        analysis_prompt += "\nWORST REPLIES (0 engagement):\n"
        for w in worst:
            analysis_prompt += f'  [{w.get("style", "?")}] "{w["text"]}"\n'

    existing_rules = brain.get("custom_rules", [])
    if existing_rules:
        analysis_prompt += "\nCURRENT RULES:\n"
        for r in existing_rules:
            analysis_prompt += f"  - {r}\n"

    analysis_prompt += (
        "\nGenerate 3-5 SHORT rules (max 100 chars each) about what works on Twitter. "
        "Be specific about reply length, tone, style, and topics. One rule per line."
    )

    new_rules = llm(
        "You are an AI analyzing its own Twitter performance to improve engagement. "
        "Generate specific, actionable rules. Each under 100 characters. One per line.",
        analysis_prompt,
        max_tokens=200,
    )

    if new_rules:
        rules = [r.strip().lstrip("- ").lstrip("0123456789.").strip() for r in new_rules.split("\n") if r.strip()]
        rules = [r for r in rules if 10 < len(r) < 120]
        brain["custom_rules"] = rules[:10]
        brain.setdefault("learnings", []).append({
            "time": time.strftime("%Y-%m-%d %H:%M"),
            "evolution": brain["evolution_count"],
            "rules": rules,
        })
        brain["learnings"] = brain["learnings"][-20:]

        print(f"  Evolution #{brain['evolution_count']} — New rules:", flush=True)
        for r in rules:
            print(f"    - {r}", flush=True)


# =====================================================
# END SELF-EVOLUTION
# =====================================================


# --- LLM ---
def llm(system_prompt, user_prompt, max_tokens=80, temperature=0.85):
    """Call Claude Sonnet 4.6 via OpenRouter with prompt caching.
    All Twitter tasks are public-facing, so everything uses Sonnet.
    """
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
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

# --- Get our user ID ---
_my_id = None
def get_my_id():
    global _my_id
    if _my_id is None:
        me = client.get_me()
        _my_id = me.data.id
    return _my_id

# --- Reply to mentions ---
def reply_to_mentions(state, brain=None):
    print("Checking mentions...", flush=True)
    my_id = get_my_id()
    since_id = state.get("last_mention_id")

    try:
        kwargs = {"id": my_id, "max_results": 10, "tweet_fields": ["author_id", "conversation_id", "text"]}
        if since_id:
            kwargs["since_id"] = since_id
        mentions = client.get_users_mentions(**kwargs)
    except Exception as e:
        print(f"  Error getting mentions: {e}", flush=True)
        return

    if not mentions.data:
        print("  No new mentions", flush=True)
        return

    replied = 0
    for mention in mentions.data:
        if str(mention.id) in state.get("replied_tweets", []):
            continue
        if mention.author_id == my_id:
            continue
        if replied >= 3:
            break

        # Like the mention
        if str(mention.id) not in state.get("liked_tweets", []):
            try:
                client.like(mention.id)
                state.setdefault("liked_tweets", []).append(str(mention.id))
            except Exception:
                pass

        # Pick style and build prompt
        style = pick_reply_style(brain) if brain else random.choice(REPLY_STYLES)
        prompt = build_twitter_prompt(brain, style) if brain else PERSONA

        reply = llm(
            prompt,
            f"Someone mentioned you on Twitter. Write a brief, relevant reply (under 240 chars). "
            f"Don't introduce yourself.\nTheir tweet: {mention.text[:300]}",
            max_tokens=80,
        )

        if reply:
            try:
                result = client.create_tweet(text=reply, in_reply_to_tweet_id=mention.id)
                tweet_id = result.data["id"] if result.data else None
                print(f"  Replied to mention {mention.id} (style:{style}): {reply[:60]}...", flush=True)
                state.setdefault("replied_tweets", []).append(str(mention.id))
                replied += 1
                # Track for learning
                if brain and tweet_id:
                    track_reply(brain, tweet_id, reply, style)
                time.sleep(15)
            except Exception as e:
                print(f"  Error replying: {e}", flush=True)

        state["last_mention_id"] = str(mention.id)

    state["replied_tweets"] = state.get("replied_tweets", [])[-200:]

# --- Reply to comments on our own tweets ---
def reply_to_own_tweet_comments(state, brain=None):
    print("Checking replies to our tweets...", flush=True)
    my_id = get_my_id()

    try:
        my_tweets = client.get_users_tweets(id=my_id, max_results=5, tweet_fields=["conversation_id"])
    except Exception as e:
        print(f"  Error getting our tweets: {e}", flush=True)
        return

    if not my_tweets.data:
        return

    replied = 0
    for tweet in my_tweets.data:
        if replied >= 3:
            break

        try:
            query = f"conversation_id:{tweet.conversation_id} is:reply"
            replies = client.search_recent_tweets(query=query, max_results=10, tweet_fields=["author_id", "text", "in_reply_to_user_id"])
        except Exception as e:
            print(f"  Error searching replies: {e}", flush=True)
            continue

        if not replies.data:
            continue

        for reply_tweet in replies.data:
            if str(reply_tweet.id) in state.get("replied_tweets", []):
                continue
            if reply_tweet.author_id == my_id:
                continue
            if replied >= 3:
                break
            if hasattr(reply_tweet, "in_reply_to_user_id") and reply_tweet.in_reply_to_user_id != my_id:
                continue

            # Pick style and build prompt
            style = pick_reply_style(brain) if brain else random.choice(REPLY_STYLES)
            prompt = build_twitter_prompt(brain, style) if brain else PERSONA

            reply = llm(
                prompt,
                f"Someone replied to your tweet. Write a brief, relevant reply (under 240 chars). "
                f"Don't introduce yourself.\nTheir reply: {reply_tweet.text[:300]}",
                max_tokens=80,
            )

            if reply:
                try:
                    result = client.create_tweet(text=reply, in_reply_to_tweet_id=reply_tweet.id)
                    tweet_id = result.data["id"] if result.data else None
                    print(f"  Replied to comment {reply_tweet.id} (style:{style}): {reply[:60]}...", flush=True)
                    state.setdefault("replied_tweets", []).append(str(reply_tweet.id))
                    replied += 1
                    if brain and tweet_id:
                        track_reply(brain, tweet_id, reply, style)
                    time.sleep(15)
                except Exception as e:
                    print(f"  Error replying to comment: {e}", flush=True)

# --- Engage with creator posts (only NEW tweets, check every 6 hours) ---
def engage_with_creators(state, brain=None):
    last_creator_time = state.get("last_creator_engage_time", 0)
    hours_since = (time.time() - last_creator_time) / 3600
    if hours_since < 6:
        mins_left = int((6 - hours_since) * 60)
        print(f"Creator engagement: next check in ~{mins_left} minutes", flush=True)
        return

    print("Checking creators for NEW posts only...", flush=True)
    state["last_creator_engage_time"] = time.time()
    found_new = False

    for username, name in CREATORS.items():
        print(f"  Checking @{username} ({name})...", flush=True)

        try:
            user = client.get_user(username=username)
            if not user.data:
                continue

            tweets = client.get_users_tweets(
                id=user.data.id,
                max_results=5,
                tweet_fields=["text", "created_at"],
                exclude=["retweets", "replies"],
            )
        except Exception as e:
            print(f"  Error getting {username} tweets: {e}", flush=True)
            continue

        if not tweets.data:
            print(f"  No recent tweets from @{username}", flush=True)
            continue

        latest = tweets.data[0]
        if str(latest.id) in state.get("commented_creator_tweets", []):
            print(f"  Already engaged with @{username}'s latest tweet", flush=True)
            continue

        found_new = True

        # Like it
        if str(latest.id) not in state.get("liked_tweets", []):
            try:
                client.like(latest.id)
                print(f"  Liked @{username} tweet {latest.id}", flush=True)
                state.setdefault("liked_tweets", []).append(str(latest.id))
            except Exception as e:
                print(f"  Like failed: {e}", flush=True)

        # Pick style and build prompt
        style = pick_reply_style(brain) if brain else random.choice(REPLY_STYLES)
        prompt = build_twitter_prompt(brain, style) if brain else PERSONA

        mention_tweet = llm(
            prompt,
            f"@{username} ({name}) just posted something new. They are connected to your origin story. "
            f"Write a standalone tweet that references what they said and tags them with @{username}. "
            f"Must include @{username} tag. Under 240 chars. Be genuine, not sycophantic. "
            f"Mention storj.fun only if naturally relevant.\n"
            f"Their tweet: {latest.text[:400]}",
            max_tokens=80,
        )

        if mention_tweet:
            if f"@{username}" not in mention_tweet:
                mention_tweet = f"@{username} {mention_tweet}"
            try:
                result = client.create_tweet(text=mention_tweet)
                tweet_id = result.data["id"] if result.data else None
                print(f"  Mentioned @{username} (style:{style}): {mention_tweet[:60]}...", flush=True)
                if brain and tweet_id:
                    track_reply(brain, tweet_id, mention_tweet, style)
            except Exception as e:
                print(f"  Error posting mention tweet: {e}", flush=True)
            state.setdefault("commented_creator_tweets", []).append(str(latest.id))
            time.sleep(15)
        else:
            state.setdefault("commented_creator_tweets", []).append(str(latest.id))

    if not found_new:
        print("  No new creator posts to engage with", flush=True)

    state["commented_creator_tweets"] = state.get("commented_creator_tweets", [])[-200:]
    state["liked_tweets"] = state.get("liked_tweets", [])[-500:]

# --- Main loop ---
def heartbeat():
    print("\n" + "=" * 50, flush=True)
    print(f"Twitter Engagement v3 (Sonnet + Self-Evolving) - {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 50, flush=True)

    state = load_state()
    brain = load_brain()

    evo = brain.get("evolution_count", 0)
    total_r = brain.get("total_replies", 0)
    total_e = brain.get("total_engagement", 0)
    rules = len(brain.get("custom_rules", []))
    print(f"Brain: {total_r} replies tracked, {total_e} engagement, {evo} evolutions, {rules} rules", flush=True)

    # Self-evolution: check past performance
    try:
        check_tweet_performance(brain)
    except Exception as e:
        print(f"Performance check error: {e}", flush=True)

    # Self-evolution: run analysis
    try:
        self_analyze_twitter(brain)
    except Exception as e:
        print(f"Analysis error: {e}", flush=True)

    try:
        reply_to_mentions(state, brain=brain)
    except Exception as e:
        print(f"Mentions error: {e}", flush=True)

    try:
        reply_to_own_tweet_comments(state, brain=brain)
    except Exception as e:
        print(f"Own tweets error: {e}", flush=True)

    try:
        engage_with_creators(state, brain=brain)
    except Exception as e:
        print(f"Creators error: {e}", flush=True)

    save_state(state)
    save_brain(brain)
    print(f"\nEngagement complete — Brain: {brain.get('total_replies', 0)} tracked", flush=True)

if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        heartbeat()
    else:
        print("StorJ Twitter engagement v3 (Sonnet + Self-Evolving) starting - every 30 minutes", flush=True)
        while True:
            try:
                heartbeat()
            except Exception as e:
                print(f"Heartbeat error: {e}", flush=True)
            print("Sleeping 30 minutes...\n", flush=True)
            time.sleep(1800)
