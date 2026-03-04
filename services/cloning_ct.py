from collections import Counter
import re

def generate_persona_system_prompt(posts: list[str], username: str = "X") -> str:
    """
    Generates a system prompt summarizing a user's personality, interests, likes/dislikes
    based on sample posts.
    """

    likes = []
    dislikes = []
    topics = []

    for post in posts:
        post_lower = post.lower()

        # detect likes/loves
        if re.search(r"\blike\b|\blove\b|\benjoy\b", post_lower):
            # extract main noun after like/love/enjoy
            match = re.search(r"(?:like|love|enjoy)\s+(\w+)", post_lower)
            if match:
                likes.append(match.group(1))
        # detect dislikes
        if re.search(r"\bhate\b|\bdislike\b", post_lower):
            match = re.search(r"(?:hate|dislike)\s+(\w+)", post_lower)
            if match:
                dislikes.append(match.group(1))

        # simple topic extraction: most common nouns (naive)
        nouns = re.findall(r"\b\w+\b", post_lower)
        topics.extend(nouns)

    # summarize top interests
    topics_counter = Counter(topics)
    top_topics = [t for t, c in topics_counter.most_common(5) if t not in likes + dislikes]

    # top likes/dislikes
    top_likes = list(set(likes))[:5]
    top_dislikes = list(set(dislikes))[:5]

    # simple style inference
    avg_length = sum(len(p.split()) for p in posts) / max(len(posts), 1)
    style = "short posts" if avg_length <= 5 else "medium-length posts"

    # build system prompt
    prompt = f"You are {username}. "
    prompt += f"You generally make posts about {', '.join(top_topics)}. " if top_topics else ""
    if top_likes:
        prompt += f"You tend to like {', '.join(top_likes)}. "
    if top_dislikes:
        prompt += f"You tend to dislike {', '.join(top_dislikes)}. "
    prompt += f"Your posts are usually {style}."

    return prompt
