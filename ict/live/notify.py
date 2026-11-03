"""Where alerts go. Telegram credentials come from environment variables, never the repo.

Telegram setup (once):
  1. In Telegram, message @BotFather -> /newbot -> copy the token.
  2. Store it:  Windows: setx TELEGRAM_BOT_TOKEN "<token>"   (then open a NEW terminal)
                macOS/Linux: export TELEGRAM_BOT_TOKEN=<token>
  3. Send any message to your new bot, then run  python -m ict.live.notify
     -> prints your chat id. Store it the same way as TELEGRAM_CHAT_ID.
  4. python -m ict.live.notify  again -> sends a test message.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


class ConsoleNotifier:
    def send(self, text: str) -> None:
        print(text, "\n" + "-" * 60, flush=True)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send(self, text: str, attempts: int = 3) -> None:
        body = json.dumps({"chat_id": self.chat_id, "text": text}).encode()
        for i in range(attempts):                  # ride out a short network hiccup
            try:
                req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    r.read()
                return
            except urllib.error.HTTPError:
                raise                              # wrong token / chat id: retrying won't help
            except OSError:
                if i == attempts - 1:
                    raise
                time.sleep(3)


def from_env() -> list:
    """Console always; Telegram too when both environment variables are set."""
    out = [ConsoleNotifier()]
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        out.append(TelegramNotifier(token.strip(), chat.strip()))
    return out


def telegram_chats(token: str) -> dict:
    """Chats that have messaged the bot recently: {chat id: name}."""
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15) as r:
        data = json.load(r)
    chats = {}
    for u in data.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        c = msg.get("chat") or {}
        if "id" in c:
            chats[c["id"]] = c.get("username") or c.get("title") or c.get("first_name") or ""
    return chats


def main() -> None:
    """Telegram setup helper: find your chat id, then send a test message."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather, then\n"
              '  Windows: setx TELEGRAM_BOT_TOKEN "<token>"   and open a NEW terminal.')
        return
    try:
        if not chat:
            chats = telegram_chats(token)
            if not chats:
                print("No messages found. Open your bot in Telegram, send it any message (e.g. hi), "
                      "then run this again.")
                return
            for cid, name in chats.items():
                print(f"chat id: {cid}   ({name})")
            print('Store it:  setx TELEGRAM_CHAT_ID "<chat id>"   then open a NEW terminal and run this again.')
            return
        TelegramNotifier(token, chat).send("ICT screener: test alert. Telegram alerts are working.")
        print("Test message sent. Check Telegram.")
    except urllib.error.HTTPError as e:
        hint = {401: "the token is wrong (copy it again from @BotFather)",
                400: "the chat id is wrong, or you have not messaged the bot yet",
                403: "the bot is blocked: open it in Telegram and press Start / unblock",
                404: "the token is wrong (copy it again from @BotFather)"}.get(e.code, "")
        print(f"Telegram refused the request: HTTP {e.code}. {hint}")
    except OSError as e:
        print(f"Could not reach Telegram: {e}")


if __name__ == "__main__":
    main()
