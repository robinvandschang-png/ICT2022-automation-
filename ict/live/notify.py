"""Where alerts go. Telegram credentials live outside the code: in `telegram.env`
next to README.md (git-ignored, never committed), or in environment variables.

Telegram setup (once):
  1. In Telegram, message @BotFather -> /newbot -> copy the token.
  2. Put it in telegram.env (Notepad is fine), one line:
         TELEGRAM_BOT_TOKEN=<token>
     (or set the environment variable TELEGRAM_BOT_TOKEN instead).
  3. Send your bot any message (Telegram keeps it for 24 hours), then run
         python -m ict.live.notify
     -> finds your chat id, saves it to telegram.env and sends a test message.
The file wins over environment variables, so editing it is all a change needs.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "telegram.env"


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


def read_settings_file(path: Path | None = None) -> dict:
    """KEY=value lines; blank lines and # comments ignored; quotes stripped."""
    out = {}
    try:
        text = Path(path or SETTINGS_FILE).read_text(encoding="utf-8-sig")   # -sig: Notepad's BOM
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'").strip()
    return out


def telegram_settings(path: Path | None = None) -> tuple[str, str]:
    """(token, chat id): telegram.env first, then environment variables."""
    f = read_settings_file(path)
    token = f.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat = f.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or ""
    return token.strip(), chat.strip()


def save_chat_id(chat_id, path: Path | None = None) -> None:
    path = Path(path or SETTINGS_FILE)
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith("TELEGRAM_CHAT_ID")]
    lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def from_env(path: Path | None = None) -> list:
    """Console always; Telegram too when a token and chat id are configured."""
    out = [ConsoleNotifier()]
    token, chat = telegram_settings(path)
    if token and chat:
        out.append(TelegramNotifier(token, chat))
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


def main(path: Path | None = None) -> None:
    """Telegram setup helper: finds and saves your chat id, then sends a test message."""
    path = Path(path or SETTINGS_FILE)
    token, chat = telegram_settings(path)
    if not token:
        print(f"No Telegram token found. Create {path} with one line:\n"
              "  TELEGRAM_BOT_TOKEN=<token from @BotFather>")
        return
    try:
        if not chat:
            chats = telegram_chats(token)
            if not chats:
                print("No messages found. Open your bot in Telegram, send it any message (e.g. hi), "
                      "then run this again within 24 hours.")
                return
            for cid, name in chats.items():
                print(f"chat id: {cid}   ({name})")
            chat = str(list(chats)[-1])           # the chat that wrote most recently
            save_chat_id(chat, path)
            print(f"Saved chat id {chat} to {path.name}.")
        TelegramNotifier(token, chat).send("ICT screener: test alert. Telegram alerts are working.")
        print("Test message sent. Check Telegram.")
    except urllib.error.HTTPError as e:
        hint = {401: "the token is wrong or was revoked (copy the current one from @BotFather)",
                400: "the chat id is wrong: delete the TELEGRAM_CHAT_ID line, message the bot, run again",
                403: "the bot is blocked: open it in Telegram and press Start / unblock",
                404: "the token is wrong or was revoked (copy the current one from @BotFather)"}.get(e.code, "")
        print(f"Telegram refused the request: HTTP {e.code}. {hint}")
    except OSError as e:
        print(f"Could not reach Telegram: {e}")


if __name__ == "__main__":
    main()
