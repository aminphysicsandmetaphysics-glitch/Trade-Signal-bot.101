# FILE: signal_bot.py (UPDATED)
# ——————————————————————————————————————————
# تغییرات اصلی:
# 1) اضافه‌شدنِ parse_list و normalize_dest برای خواندن DESTS به‌صورت لیست
# 2) رزولوشنِ مقصدها یک‌بار در start و نگه‌داری در self.dest_entities
# 3) ارسال/فوروارد پیام به همه‌ی مقاصد در یک حلقه
# 4) لاگ‌های شفاف برای مقاصد نامعتبر

import os, json, ast, re
import asyncio
import logging
from typing import List, Union
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

logger = logging.getLogger("signal_bot")
logger.setLevel(logging.INFO)

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "signal_bot")

# منابع (کانال‌های مبدا) می‌تواند لیست JSON/CSV/… باشد
RAW_SOURCES = os.getenv("SOURCES", "")
RAW_DESTS   = os.getenv("DESTS",   "")

# ——— helpers ———
def parse_list(val: str) -> List[str]:
    if not val:
        return []
    s = val.strip()
    # JSON
    try:
        data = json.loads(s)
        if isinstance(data, (list, tuple)):
            return [str(x) for x in data]
    except Exception:
        pass
    # Python literal (e.g. ["a", "b"]) 
    try:
        data = ast.literal_eval(s)
        if isinstance(data, (list, tuple)):
            return [str(x) for x in data]
    except Exception:
        pass
    # CSV fallback
    return [x.strip() for x in s.split(',') if x.strip()]

def normalize_channel_id(x: Union[str,int]) -> Union[int,str]:
    s = str(x).strip().strip('"').strip("'")
    if s.startswith('@'):
        return s  # username
    if re.fullmatch(r"-?\d+", s):
        # برای کانال‌های عددی مطمئن شو -100 دارد
        if not s.startswith('-100'):
            s = '-100' + s.lstrip('+').lstrip('-')
        try:
            return int(s)
        except Exception:
            return s
    return s

class SignalBot:
    def __init__(self):
        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        self.source_ids = [normalize_channel_id(x) for x in parse_list(RAW_SOURCES)]
        self.dest_raw   = [normalize_channel_id(x) for x in parse_list(RAW_DESTS)]
        self.dest_entities = []  # filled in start()

    async def _resolve_sources(self):
        ok = []
        for s in self.source_ids:
            try:
                ent = await self.client.get_entity(s)
                ok.append(ent)
                logger.info(f"[INFO] Listening source: {getattr(ent,'title',getattr(ent,'username',ent))} (id={getattr(ent,'id',s)})")
            except Exception as e:
                logger.error(f"[ERROR] Cannot access source '{s}': {e}")
        self.source_entities = ok

    async def _resolve_dests(self):
        ok = []
        for d in self.dest_raw:
            try:
                ent = await self.client.get_entity(d)
                ok.append(ent)
            except Exception as e:
                logger.error(f"[ERROR] Cannot access destination '{d}': {e}")
        self.dest_entities = ok
        if not self.dest_entities:
            logger.error("[ERROR] No valid destinations resolved. Check DESTS and membership.")

    async def start(self):
        logger.info("Starting Telegram client...")
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError("Session is not authorized. Recreate session.")

        # resolve once
        await self._resolve_sources()
        await self._resolve_dests()

        # اگر source مشخص شده، روی آن فیلتر بگذار؛ در غیر اینصورت همه‌ی چت‌ها را می‌گیرد
        @self.client.on(events.NewMessage(chats=[getattr(e,'id',e) for e in getattr(self,'source_entities',[])]) )
        async def handler(event: events.NewMessage.Event):
            msg = event.message
            # forward to all destinations
            for dest in self.dest_entities:
                try:
                    await self.client.forward_messages(dest, msg)
                except FloodWaitError as fw:
                    logger.warning(f"[WARN] flood wait {fw.seconds}s while forwarding to {getattr(dest,'id',dest)}")
                    await asyncio.sleep(fw.seconds)
                    try:
                        await self.client.forward_messages(dest, msg)
                    except Exception as e2:
                        logger.warning(f"[WARN] retry failed for {getattr(dest,'id',dest)}: {e2}")
                except Exception as e:
                    logger.warning(f"[WARN] failed to forward to {getattr(dest,'id',dest)}: {e}")

        logger.info("[INFO] Client started. Waiting for messages...")
        await self.client.run_until_disconnected()

if __name__ == "__main__":
    bot = SignalBot()
    try:
        bot.client.loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        pass
