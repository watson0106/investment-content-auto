"""
X (Twitter) 投稿モジュール
各パイプラインから import して使う共通モジュール
"""
import os
import tweepy
from dotenv import load_dotenv

# .env は investment-content-auto を共通参照
ENV_PATH = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(ENV_PATH)


def _get_client():
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def post_tweet(text: str):
    """
    ツイートを投稿する。
    成功時はツイートIDを返す。失敗時は None を返す。
    """
    if len(text) > 280:
        text = text[:277] + "..."

    try:
        client = _get_client()
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        print(f"[X] 投稿成功: https://x.com/i/web/status/{tweet_id}")
        return tweet_id
    except Exception as e:
        print(f"[X] 投稿失敗: {e}")
        return None


if __name__ == "__main__":
    # 動作テスト
    result = post_tweet("テスト投稿です。自動投稿の動作確認中。#投資 #日本株")
    if result:
        print("テスト成功")
    else:
        print("テスト失敗")
