import asyncio
import re
from typing import List, Dict, Any

import tweepy
import discord

from .logger import logger
from .monitordb import MonitorDB
from .twauth import TwitterAuth


class TweetCollectStream(tweepy.Stream):
    def __init__(
        self,
        client: discord.Client,
        tw_auth: TwitterAuth,
        monitor_db: MonitorDB,
        loop,
    ):
        super().__init__(
            tw_auth.consumer_key,
            tw_auth.consumer_secret,
            tw_auth.access_token,
            tw_auth.access_secret,
        )

        self.client = client
        self.monitor_db = monitor_db
        self.loop = loop
        self.thread = None
        self.user_id_map = None

    def resume(self):
        monitors: Dict[str:Any] = self.monitor_db.select_all()
        user_id_map: Dict[int : List[Dict[str:Any]]] = {}
        for m in monitors:
            tid = m["twitter_id"]
            if tid not in user_id_map:
                user_id_map[tid] = []
            user_id_map[tid].append(m)

        if self.thread:
            self.disconnect()

        self.thread = self.filter(
            follow=list(map(str, user_id_map.keys())), threaded=True
        )
        self.user_id_map = user_id_map

    def disconnect(self):
        super().disconnect()
        # Wait stream blocking I/O thread
        if self.thread:
            self.thread.join()
            self.thread = None

    def on_status(self, status):
        # Get new tweet
        # For some reason, get tweets of other users

        user_id = status.user.id
        if user_id not in self.user_id_map:
            return

        # Format tweet
        expand_text = status.text
        for e in status.entities["urls"]:
            expand_text = expand_text.replace(e["url"], e["display_url"])

        for m in self.user_id_map[user_id]:
            # Not matched
            if m["match_ptn"] and not re.search(m["match_ptn"], expand_text):
                logger.debug(
                    "[DEBUG] status.text is not matched with regular expression"
                )
                continue

            url = f"https://twitter.com/{status.user.screen_name}/status/{status.id}"
            channel = self.client.get_channel(m["channel_id"])
            future = asyncio.run_coroutine_threadsafe(channel.send(url), self.loop)
            future.result()

    def on_error(self, status):
        logger.error(status)