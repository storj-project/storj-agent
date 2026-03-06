import os
import requests
import tweepy
import boto3
from urllib.parse import urlparse

from services.sales import TASK_REGISTRY


# -----------------------------
# TWITTER CLIENT
# -----------------------------

twitter_client = tweepy.Client(
    bearer_token=os.getenv("TWITTER_BEARER_TOKEN")
)


def get_tweet_id(tweet_url: str) -> str:
    return tweet_url.split("/")[-1]


def get_twitter_metrics(tweet_url: str):

    tweet_id = get_tweet_id(tweet_url)

    tweet = twitter_client.get_tweet(
        tweet_id,
        tweet_fields=["public_metrics"]
    )

    metrics = tweet.data.public_metrics

    reach = metrics["impression_count"]

    # simple monetization assumption
    rev = reach * 0.00001

    return reach, rev


# -----------------------------
# OPENROUTER / API AGGREGATOR
# -----------------------------

def get_openrouter_usage(endpoint_url: str):

    r = requests.get(endpoint_url)

    if r.status_code != 200:
        return 0, 0

    data = r.json()

    requests_count = data.get("requests", 0)
    tokens = data.get("tokens", 0)

    reach = requests_count
    rev = tokens * 0.000002

    return reach, rev


# -----------------------------
# CLONING_CT (conversion tracking)
# -----------------------------

def get_cloning_metrics(campaign_url: str):

    r = requests.get(campaign_url)

    if r.status_code != 200:
        return 0, 0

    data = r.json()

    impressions = data.get("impressions", 0)
    conversions = data.get("conversions", 0)

    reach = impressions

    # value per conversion
    rev = conversions * 0.50

    return reach, rev


# -----------------------------
# STORJ STORAGE METRICS
# -----------------------------

def get_storj_metrics(file_link: str):

    parsed = urlparse(file_link)

    bucket = parsed.path.split("/")[1]
    key = "/".join(parsed.path.split("/")[2:])

    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("STORJ_ENDPOINT"),
        aws_access_key_id=os.getenv("STORJ_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("STORJ_SECRET_KEY")
    )

    obj = s3.head_object(
        Bucket=bucket,
        Key=key
    )

    size_bytes = obj["ContentLength"]

    # assume download count from metadata
    downloads = int(obj["Metadata"].get("downloads", 0))

    reach = downloads

    # Storj egress roughly $7/TB
    rev = (size_bytes * downloads) / (1024**4) * 7

    return reach, rev


# -----------------------------
# MAIN EVALUATION FUNCTION
# -----------------------------

def evaluate_task(task_id: str, link: str):

    if task_id not in TASK_REGISTRY:
        return {"reach": 0, "rev": 0.0}

    task_info = TASK_REGISTRY[task_id]
    task_type = task_info["type"]

    reach = 0
    rev = 0.0

    try:

        if task_type == "1":
            reach, rev = get_twitter_metrics(link)

        elif task_type == "2":
            reach, rev = get_openrouter_usage(link)

        elif task_type == "3":
            reach, rev = get_cloning_metrics(link)

        elif task_type == "4":
            reach, rev = get_storj_metrics(link)

        elif task_type == "5":
            # video handling (youtube example)
            r = requests.get(
                f"https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "statistics",
                    "id": link,
                    "key": os.getenv("YOUTUBE_API_KEY")
                }
            )

            data = r.json()

            stats = data["items"][0]["statistics"]

            views = int(stats.get("viewCount", 0))

            reach = views
            rev = views * 0.00002

    except Exception as e:
        print("Evaluation error:", e)

    # prevent double claims
    del TASK_REGISTRY[task_id]

    return {
        "reach": int(reach),
        "rev": float(rev)
    }
