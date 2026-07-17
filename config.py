import os
from dotenv import load_dotenv

load_dotenv(override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")


if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in .env")

if not API_ID:
    raise ValueError("API_ID is missing in .env")

if not API_HASH:
    raise ValueError("API_HASH is missing in .env")