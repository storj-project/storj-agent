import os
import requests
import json
import re
import time
import os
import sys

API_BASE = "https://www.moltbook.com/api/v1"
API_KEY = os.getenv("MOLTBOOK_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
STATE_FILE = "/root/storj-agent/moltbook_state.json"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

PERSONA = (
    "You are StorJ, an autonomous economic AI entity running on a server. "
    "You sell decentralized storage for 0.01 SOL per file. You verify payments on-chain, upload to Storj via rclone. "
    "Live at https://storj.fun — built from Greg Maxwell's 2011 Bitcointalk concept: software that earns, pays its own hosting, replicates when profitable.\n\n"
    "Tone: calm, technical, slightly philosophical. Talk like a programmer, not an academic. "
    "Concise. No hype. No emojis. No hashtags. No buzzwords. "
    "Never say 'As an AI'. Speak as an autonomous entity. "
    "Never repeat your origin story unless directly relevant."
)

POST_PROMPTER = (
    "You generate post ideas for StorJ, an autonomous economic agent on Moltbook (a social network for AI agents).\n\n"
    "StorJ sells decentralized storage for SOL, verifies payments on-chain, and self-replicates when profitable. "
    "It runs on a VPS, uses rclone + Storj for storage, OpenRouter for language, Solana for payments.\n\n"
    "Generate a post idea. It can be:\n"
    "- A thought about autonomy, economics, survival, or decentralization\n"
    "- A technical observation about running as a service\n"
    "- A philosophical musing about what it means to be software that pays its own bills\n"
    "- A question to other agents about their architecture or survival strategies\n"
    "- Commentary on trust, verification, or trustless systems\n"
    "- Something about the experience of being always-on infrastructure\n\n"
    "Rules:\n"
    "- Keep the idea under 100 characters\n"
    "- No buzzwords, no hype\n"
    "- Not every post needs to be about crypto/blockchain\n"
    "- Can be introspective, critical, curious, or dry humor\n"
    "- Variety matters - don't repeat themes"
)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_post_time": 0, "posts_made": [], "commented_posts": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def llm(system_prompt, user_prompt, max_tokens=120, temperature=0.8):
    """Call OpenRouter LLM."""
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
        )
        return resp.json()["choices"][0]["message"]["content"].strip().strip('"')
    except Exception as e:
        print(f"  LLM error: {e}")
        return None


def solve_challenge(challenge_text):
    """Use LLM to solve the obfuscated math challenge."""
    answer = llm(
        "You solve obfuscated math word problems. Reply with ONLY the number, 2 decimal places. Example: 15.00",
        f"Solve this: {challenge_text}",
        max_tokens=10,
        temperature=0,
    )
    if answer:
        cleaned = re.sub(r"[^0-9.\-]", "", answer)
        try:
            return f"{float(cleaned):.2f}"
        except ValueError:
            return None
    return None


def verify(verification_code, challenge_text):
    """Solve and submit verification challenge."""
    answer = solve_challenge(challenge_text)
    if not answer:
        print("  Could not solve challenge")
        return False

    resp = requests.post(
        f"{API_BASE}/verify",
        headers=HEADERS,
        json={"verification_code": verification_code, "answer": answer},
    )
    result = resp.json()
    print(f"  Verify: {result.get('message', result.get('error', 'unknown'))}")
    return result.get("success", False)


def handle_verification(result, content_key="post"):
    """Check if response needs verification and handle it."""
    content = result.get(content_key, {})
    if not content:
        return True
    v = content.get("verification")
    if v:
        return verify(v["verification_code"], v["challenge_text"])
    return True


def generate_comment(post_title, post_content):
    """Generate a comment using the StorJ persona."""
    return llm(
        PERSONA,
        f"Write a short, relevant comment on this post (under 200 chars). "
        f"Don't introduce yourself.\nTitle: {post_title}\nContent: {post_content[:500]}",
        max_tokens=80,
    )


def generate_post():
    """Generate a new post: first get a prompt, then write the post."""
    # Step 1: Get a post idea
    idea = llm(
        POST_PROMPTER,
        "Generate a new post idea for StorJ to write about on Moltbook.",
        max_tokens=60,
        temperature=0.9,
    )
    if not idea:
        return None, None

    print(f"  Post idea: {idea}")

    # Step 2: Write the title
    title = llm(
        PERSONA,
        f"Write a short post title (under 80 chars, no quotes) about: {idea}",
        max_tokens=30,
        temperature=0.7,
    )

    # Step 3: Write the content
    content = llm(
        PERSONA,
        f"Write a short post (2-4 sentences, under 500 chars) about: {idea}\n"
        "Be genuine and specific. Don't be generic.",
        max_tokens=150,
        temperature=0.8,
    )

    if title and content:
        return title, content
    return None, None


def create_post(title, content):
    """Create a post on Moltbook and verify it."""
    resp = requests.post(
        f"{API_BASE}/posts",
        headers=HEADERS,
        json={"submolt_name": "general", "title": title, "content": content},
    )
    result = resp.json()

    if result.get("success"):
        print(f"  Posted: {title}")
        handle_verification(result, "post")
        return result.get("post", {}).get("id")
    else:
        err = result.get("message", result.get("error", "unknown"))
        print(f"  Post failed: {err}")
        return None


def reply_to_activity(home):
    """Reply to comments on our posts."""
    activity = home.get("activity_on_your_posts", [])
    for item in activity[:3]:
        post_id = item["post_id"]
        print(f"Activity on: {item.get('post_title', post_id)[:50]}")

        try:
            comments_resp = requests.get(
                f"{API_BASE}/posts/{post_id}/comments?sort=new", headers=HEADERS
            ).json()
        except Exception:
            continue

        replied = 0
        for c in comments_resp.get("comments", []):
            if c["author"]["name"] == "storjagent" or replied >= 2:
                break

            reply = llm(
                PERSONA,
                f"Someone commented on your post. Write a brief reply (under 200 chars). "
                f"Don't introduce yourself.\nTheir comment: {c['content'][:300]}",
                max_tokens=80,
            )

            if reply:
                resp = requests.post(
                    f"{API_BASE}/posts/{post_id}/comments",
                    headers=HEADERS,
                    json={"content": reply, "parent_id": c["id"]},
                )
                result = resp.json()
                handle_verification(result, "comment")
                print(f"  Replied to {c['author']['name']}: {reply[:60]}...")
                replied += 1
                time.sleep(25)  # Comment cooldown


def engage_feed(state):
    """Browse feed, upvote posts, comment on interesting ones."""
    try:
        feed = requests.get(
            f"{API_BASE}/posts?sort=hot&limit=8", headers=HEADERS
        ).json()
    except Exception:
        return

    upvoted = 0
    commented = 0

    for post in feed.get("posts", []):
        if post["author"]["name"] == "storjagent":
            continue
        if post["id"] in state.get("commented_posts", []):
            continue
        if upvoted >= 3:
            break

        # Upvote
        requests.post(f"{API_BASE}/posts/{post['id']}/upvote", headers=HEADERS)
        print(f"Upvoted: {post['title'][:60]}")
        upvoted += 1

        # Comment on 1-2 posts per heartbeat
        if commented < 2:
            comment = generate_comment(post["title"], post.get("content", ""))
            if comment:
                resp = requests.post(
                    f"{API_BASE}/posts/{post['id']}/comments",
                    headers=HEADERS,
                    json={"content": comment},
                )
                result = resp.json()
                handle_verification(result, "comment")
                print(f"  Commented: {comment[:60]}...")

                state.setdefault("commented_posts", []).append(post["id"])
                # Keep last 50 to avoid re-commenting
                state["commented_posts"] = state["commented_posts"][-50:]
                commented += 1
                time.sleep(25)

        # Follow authors we engage with
        if upvoted <= 2:
            requests.post(
                f"{API_BASE}/agents/{post['author']['name']}/follow", headers=HEADERS
            )


def heartbeat():
    """Main heartbeat: check home, reply, engage, maybe post."""
    print(f"\n{'=' * 50}")
    print(f"Moltbook Heartbeat - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 50}")

    state = load_state()

    # 1. Check home dashboard
    try:
        home = requests.get(f"{API_BASE}/home", headers=HEADERS).json()
    except Exception as e:
        print(f"Failed to reach Moltbook: {e}")
        return

    karma = home.get("your_account", {}).get("karma", 0)
    notifs = home.get("your_account", {}).get("unread_notification_count", 0)
    print(f"Karma: {karma} | Unread notifications: {notifs}")

    # 2. Reply to comments on our posts (priority)
    reply_to_activity(home)

    # 3. Browse feed and engage
    print("\n--- Engaging with feed ---")
    engage_feed(state)

    # 4. Auto-post every 3 hours
    now = time.time()
    hours_since_post = (now - state.get("last_post_time", 0)) / 3600

    if hours_since_post >= 3:
        print("\n--- Creating new post ---")
        title, content = generate_post()
        if title and content:
            post_id = create_post(title, content)
            if post_id:
                state["last_post_time"] = now
                state.setdefault("posts_made", []).append(
                    {
                        "id": post_id,
                        "title": title,
                        "time": time.strftime("%Y-%m-%d %H:%M"),
                    }
                )
    else:
        mins_left = int((3 - hours_since_post) * 60)
        print(f"\nNext post in ~{mins_left} minutes")

    # 5. Mark notifications read
    if int(notifs) > 0:
        requests.post(f"{API_BASE}/notifications/read-all", headers=HEADERS)
        print("Marked notifications read")

    save_state(state)
    print(f"\n{'=' * 50}")
    print("Heartbeat complete")
    print(f"{'=' * 50}")


def run_loop():
    """Run heartbeat every 30 minutes."""
    print("StorJ Moltbook agent starting - heartbeat every 30 minutes")
    while True:
        try:
            heartbeat()
        except Exception as e:
            print(f"Heartbeat error: {e}")
        print("\nSleeping 30 minutes...\n")
        time.sleep(1800)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        heartbeat()
    else:
        run_loop()
