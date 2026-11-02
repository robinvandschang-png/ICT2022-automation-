"""Where alerts go. Telegram credentials come from environment variables, never the repo.

Telegram setup (once):
  1. In Telegram, message @BotFather -> /newbot -> copy the token.
  2. Send any message to your new bot, then open
     https://api.telegram.org/bot<TOKEN>/getUpdates and copy "chat":{"id": ...}.
  3. export TELEGRAM_BOT_TOKEN=...  and  export TELEGRAM_CHAT_ID=...
"""
from __future__ import annotations

import json
import os
import urllib.request


class ConsoleNotifier:
    def send(self, text: str) -> None:
        print(text, "\n" + "-" * 60, flush=True)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        body = json.dumps({"chat_id": self.chat_id, "text": text}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()


def from_env() -> list:
    """Console always; Telegram too when both environment variables are set."""
    out = [ConsoleNotifier()]
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        out.append(TelegramNotifier(token, chat))
    return out
