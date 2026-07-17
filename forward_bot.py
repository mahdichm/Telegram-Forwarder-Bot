import os
import json
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler,
    ConversationHandler, 
    MessageHandler, 
    ContextTypes, 
    filters,
)
from telethon.errors import SessionPasswordNeededError
from telethon import TelegramClient, events
from config import API_ID, API_HASH, BOT_TOKEN


SESSION_PATH = "sessions"
DATA_FILE = "users_data.json"

os.makedirs(SESSION_PATH, exist_ok=True)


def load_users_data():
    if not os.path.exists(DATA_FILE):
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_users_data():
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(USERS_DATA, file, ensure_ascii=False, indent=2)


USERS_DATA = load_users_data()
ACTIVE_CLIENTS = {}

def get_session_name(user_id):
    return os.path.join(SESSION_PATH, str(user_id))


(
    START,
    WAITING_FOR_PHONE,
    WAITING_FOR_CODE,
    WAITING_FOR_PASSWORD,
    MAIN_MENU,
    ADD_SOURCE,
    ADD_DESTINATION,
    VIEW_SOURCE_LIST,
    VIEW_DEST_LIST,
    EDIT_SOURCE,
    EDIT_DESTINATION,
) = range(11)

WELCOME_MESSAGE = (
    "Welcome to ForwardBot!\n\n"
    "You can automatically forward content from your favorite public channels to your target channels!\n"
    "You have full control of sources, destinations, and filtering rules via inline buttons.\n\n"
    "Let's get started"
)

def get_user_data(user_id):
    user_id = str(user_id)

    if user_id not in USERS_DATA:
        USERS_DATA[user_id] = {
            "sources": [],
            "destinations": [],
            "forward_active": False,
        }
        save_users_data()

    return USERS_DATA[user_id]

# ---------- SESSION LOGIN FLOW ---------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Start Bot", callback_data="start_bot")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(WELCOME_MESSAGE, reply_markup=reply_markup)
    return START

async def start_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Please enter your phone number with country code (e.g. +12025550123):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return WAITING_FOR_PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user_id = update.message.from_user.id
    context.user_data["phone"] = phone
    session_name = get_session_name(user_id)
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.connect()
    context.user_data["client"] = client
    if not await client.is_user_authorized():
        try:
            await client.send_code_request(phone)
            await update.message.reply_text("A code was sent to your Telegram! Please enter the code:")
            return WAITING_FOR_CODE
        except Exception as e:
            await update.message.reply_text(f"Something went wrong: {e}\nPlease try again.")
            await client.disconnect()
            return ConversationHandler.END
    else:
        await client.disconnect()
        await update.message.reply_text("You're already logged in! No need to login again.")

        user = get_user_data(user_id)
        user["forward_active"] = False
        save_users_data()

        await show_main_menu(update, context)
        return MAIN_MENU

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id
    client = context.user_data.get("client")
    phone = context.user_data.get("phone")

    try:
        try:
            await client.sign_in(phone, code)
            await client.disconnect()

            user = get_user_data(user_id)
            user["forward_active"] = False
            save_users_data()

            await update.message.reply_text(
                "âœ… Your session was created successfully!\n"
                "Now you have access to all ForwardBot features. ًںژ‰"
            )
            await show_main_menu(update, context)
            return MAIN_MENU

        except SessionPasswordNeededError:
            await update.message.reply_text(
                "Two-Step Verification is enabled!\n"
                "Please enter your Telegram password:"
            )
            return WAITING_FOR_PASSWORD

    except Exception as e:
        await update.message.reply_text(f"Login failed: {e}\nPlease try again.")
        await client.disconnect()
        return ConversationHandler.END

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    client = context.user_data.get("client")

    try:
        await client.sign_in(password=password)
        await client.disconnect()

        user = get_user_data(user_id)
        user["forward_active"] = False
        save_users_data()

        await update.message.reply_text(
            "âœ… Your session was created successfully!\n"
            "Now you have access to all ForwardBot features. ًںژ‰"
        )
        await show_main_menu(update, context)
        return MAIN_MENU

    except Exception as e:
        await update.message.reply_text(f"Password incorrect or login failed: {e}\nPlease try again.")
        await client.disconnect()
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(" Operation canceled.", reply_markup=ReplyKeyboardRemove())
    client = context.user_data.get("client")
    if client:
        await client.disconnect()
    return ConversationHandler.END

# ------------------ MAIN MENU & HANDLERS --------------------

MAIN_MENU_TEXT = (
    "<b>ForwardBot Main Menu</b>\n\n"
    "Manage your sources, destinations, bot status, settings and filters."
)

def build_main_menu(user_id):
    user = get_user_data(user_id)
    forward_status = "Start Bot" if not user.get("forward_active") else "Stop Bot"
    keyboard = [
        [
            InlineKeyboardButton("Add Source", callback_data="add_source"),
            InlineKeyboardButton("Add Destination", callback_data="add_destination"),
        ],
        [
            InlineKeyboardButton("Source List", callback_data="source_list"),
            InlineKeyboardButton("Destination List", callback_data="destination_list"),
        ],
        [
            InlineKeyboardButton(forward_status, callback_data="toggle_forward"),
            InlineKeyboardButton("Forward Settings", callback_data="forward_settings"),
        ],
        [
            InlineKeyboardButton("Rules & Filters", callback_data="rules_filters"),
            InlineKeyboardButton("Status", callback_data="status"),
        ],
        [InlineKeyboardButton("Back", callback_data="back_to_start")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    target = update.message if hasattr(update, "message") and update.message else update.callback_query.message
    await target.reply_text(
        MAIN_MENU_TEXT,
        reply_markup=build_main_menu(user_id),
        parse_mode="HTML",
    )
    return MAIN_MENU

async def start_forwarding(user_id):
    user_id = str(user_id)
    user = get_user_data(user_id)

    if user_id in ACTIVE_CLIENTS:
        return True, "Forwarding is already running."

    sources = user.get("sources", [])
    destinations = user.get("destinations", [])

    if not sources:
        return False, "Please add at least one source first."

    if not destinations:
        return False, "Please add at least one destination first."

    session_file = get_session_name(user_id) + ".session"
    if not os.path.exists(session_file):
        return False, "You are not logged in yet. Please /start and login first."

    client = TelegramClient(get_session_name(user_id), API_ID, API_HASH)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return False, "Your Telegram session is not authorized. Please login again."

        async def forward_handler(event):
            for destination in destinations:
                try:
                    await client.forward_messages(destination, event.message)
                except Exception as e:
                    print(f"Forward failed to {destination}: {e}")

        client.add_event_handler(
            forward_handler,
            events.NewMessage(chats=sources)
        )

        ACTIVE_CLIENTS[user_id] = {
            "client": client,
            "handler": forward_handler,
        }

        user["forward_active"] = True
        save_users_data()

        return True, "Forwarding started successfully."

    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass

        return False, f"Could not start forwarding: {e}"


async def stop_forwarding(user_id):
    user_id = str(user_id)
    user = get_user_data(user_id)

    active = ACTIVE_CLIENTS.pop(user_id, None)

    if active:
        client = active["client"]
        handler = active["handler"]

        try:
            client.remove_event_handler(handler)
            await client.disconnect()
        except Exception as e:
            print(f"Stop forwarding failed: {e}")

    user["forward_active"] = False
    save_users_data()

    return True, "Forwarding stopped."

# Start/Stop Forwarding (toggle)
async def toggle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user = get_user_data(user_id)

    if user.get("forward_active"):
        ok, message = await stop_forwarding(user_id)
    else:
        ok, message = await start_forwarding(user_id)

    await query.message.reply_text(message)
    await query.message.edit_reply_markup(build_main_menu(user_id))

    return MAIN_MENU


# Add Source
async def add_source_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Please enter the @username or t.me link of the source channel/group you want to add:\n\nExample: @channel1 or https://t.me/channel1",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_SOURCE

async def add_source_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    txt = update.message.text.strip()
    username = None
    if txt.startswith("https://t.me/"):
        username = txt.split("https://t.me/")[1].split("/")[0]
        if not username.startswith("@"):
            username = "@" + username
    elif txt.startswith("@"):
        username = txt
    else:
        await update.message.reply_text(" Please enter a valid username (starts with @) or t.me link.")
        return ADD_SOURCE

    users = get_user_data(user_id)
    if username not in users["sources"]:
        users["sources"].append(username)
        save_users_data()
        await update.message.reply_text(f" Source channel {username} added successfully.")
    else:
        await update.message.reply_text(f"This channel is already in your sources list.")

    await show_main_menu(update, context)
    return MAIN_MENU

# Add Destination
async def add_destination_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Please enter the @username or t.me link of the destination channel/group you want to add:\n\nExample: @destination1 or https://t.me/destination1",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_DESTINATION

async def add_destination_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    txt = update.message.text.strip()
    username = None

    if txt.startswith("https://t.me/"):
        username = txt.split("https://t.me/")[1].split("/")[0]
        if not username.startswith("@"):
            username = "@" + username
    elif txt.startswith("@"):
        username = txt
    else:
        await update.message.reply_text(" Please enter a valid username (starts with @) or t.me link.")
        return ADD_DESTINATION

    users = get_user_data(user_id)
    if username not in users["destinations"]:
        users["destinations"].append(username)
        save_users_data()
        await update.message.reply_text(f"âœ… Destination channel {username} added successfully.")
    else:
        await update.message.reply_text("â„¹ï¸ڈ This channel is already in your destinations list.")

    await show_main_menu(update, context)
    return MAIN_MENU

# Source List (with Remove/Edit)
def build_source_list_keyboard(user_id):
    users = get_user_data(user_id)
    keyboard = []
    for idx, username in enumerate(users["sources"], 1):
        keyboard.append([
            InlineKeyboardButton(f"{idx}. {username}", callback_data="noop"),
            InlineKeyboardButton("Remove", callback_data=f"remove_source__{username}"),
            InlineKeyboardButton("Edit", callback_data=f"edit_source__{username}"),
        ])
    keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

async def source_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
    "<b>Your current source channels:</b>",
    reply_markup=build_source_list_keyboard(user_id),
    parse_mode="HTML"
)
    return VIEW_SOURCE_LIST

async def handle_source_remove_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = update.callback_query.data

    if data.startswith("remove_source__"):
        username = data.replace("remove_source__", "")
        users = get_user_data(user_id)

        if username in users["sources"]:
            users["sources"].remove(username)
            save_users_data()
            await update.callback_query.answer(f"Channel {username} removed.")
        else:
            await update.callback_query.answer("Channel not found.")

        await update.callback_query.message.edit_reply_markup(build_source_list_keyboard(user_id))
        return VIEW_SOURCE_LIST

    elif data.startswith("edit_source__"):
        username = data.replace("edit_source__", "")
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            f"Send a new @username or t.me link to edit {username} or type /cancel",
        )
        context.user_data["editing_source"] = username
        return EDIT_SOURCE

async def edit_source_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    old_username = context.user_data.get("editing_source")
    txt = update.message.text.strip()
    username = None

    if txt.startswith("https://t.me/"):
        username = txt.split("https://t.me/")[1].split("/")[0]
        if not username.startswith("@"):
            username = "@" + username
    elif txt.startswith("@"):
        username = txt
    else:
        await update.message.reply_text(" Please enter a valid username (starts with @) or t.me link.")
        return EDIT_SOURCE

    users = get_user_data(user_id)
    if old_username in users["sources"]:
        users["sources"][users["sources"].index(old_username)] = username
        save_users_data()
        await update.message.reply_text(f"âœڈï¸ڈ Channel {old_username} updated to {username}.")
    else:
        await update.message.reply_text("Channel not found!")

    await show_main_menu(update, context)
    return MAIN_MENU

# Destination List (with Remove/Edit)
def build_dest_list_keyboard(user_id):
    users = get_user_data(user_id)
    keyboard = []
    for idx, username in enumerate(users["destinations"], 1):
        keyboard.append([
            InlineKeyboardButton(f"{idx}. {username}", callback_data="noop_dest"),
            InlineKeyboardButton("Remove", callback_data=f"remove_dest__{username}"),
            InlineKeyboardButton("Edit", callback_data=f"edit_dest__{username}"),
        ])
    keyboard.append([InlineKeyboardButton("Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

async def destination_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
    "<b>Your current destination channels:</b>",
    reply_markup=build_dest_list_keyboard(user_id),
    parse_mode="HTML"
)
    return VIEW_DEST_LIST

async def handle_dest_remove_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = update.callback_query.data

    if data.startswith("remove_dest__"):
        username = data.replace("remove_dest__", "")
        users = get_user_data(user_id)

        if username in users["destinations"]:
            users["destinations"].remove(username)
            save_users_data()
            await update.callback_query.answer(f"Channel {username} removed.")
        else:
            await update.callback_query.answer("Channel not found.")

        await update.callback_query.message.edit_reply_markup(build_dest_list_keyboard(user_id))
        return VIEW_DEST_LIST

    elif data.startswith("edit_dest__"):
        username = data.replace("edit_dest__", "")
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            f"Send a new @username or t.me link to edit {username} or type /cancel",
        )
        context.user_data["editing_dest"] = username
        return EDIT_DESTINATION

async def edit_dest_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    old_username = context.user_data.get("editing_dest")
    txt = update.message.text.strip()
    username = None

    if txt.startswith("https://t.me/"):
        username = txt.split("https://t.me/")[1].split("/")[0]
        if not username.startswith("@"):
            username = "@" + username
    elif txt.startswith("@"):
        username = txt
    else:
        await update.message.reply_text(" Please enter a valid username (starts with @) or t.me link.")
        return EDIT_DESTINATION

    users = get_user_data(user_id)
    if old_username in users["destinations"]:
        users["destinations"][users["destinations"].index(old_username)] = username
        save_users_data()
        await update.message.reply_text(f"âœڈï¸ڈ Channel {old_username} updated to {username}.")
    else:
        await update.message.reply_text("Channel not found!")

    await show_main_menu(update, context)
    return MAIN_MENU

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await show_main_menu(update, context)
    return MAIN_MENU

# Forward Settings
async def forward_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "âڑ™ï¸ڈ Forward Settings menu coming soon!"
    )
    await show_main_menu(update, context)
    return MAIN_MENU

# Rules & Filters
async def rules_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "ًںژ›ï¸ڈ Rules & Filters menu coming soon!"
    )
    await show_main_menu(update, context)
    return MAIN_MENU

# Status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    stat = (
    "ForwardBot Status:\n"
    f"Forwarding: {'Active' if user.get('forward_active') else 'Inactive'}\n"
    f"Sources: {len(user.get('sources', []))}\n"
    f"Destinations: {len(user.get('destinations', []))}\n"
    f"Session: {'Registered' if os.path.exists(os.path.join(SESSION_PATH, f'{user_id}.session')) else 'Not Registered'}"
)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(stat)
    await show_main_menu(update, context)
    return MAIN_MENU

# ------------- HANDLER/CONV SETUP -------------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START: [
                CallbackQueryHandler(start_bot_callback, pattern="^start_bot$"),
            ],
            WAITING_FOR_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)
            ],
            WAITING_FOR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)
            ],
            WAITING_FOR_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)
            ],
            MAIN_MENU: [
                CallbackQueryHandler(add_source_start, pattern="^add_source$"),
                CallbackQueryHandler(add_destination_start, pattern="^add_destination$"),
                CallbackQueryHandler(source_list, pattern="^source_list$"),
                CallbackQueryHandler(destination_list, pattern="^destination_list$"),
                CallbackQueryHandler(toggle_forward, pattern="^toggle_forward$"),
                CallbackQueryHandler(forward_settings, pattern="^forward_settings$"),
                CallbackQueryHandler(rules_filters, pattern="^rules_filters$"),
                CallbackQueryHandler(status, pattern="^status$"),
                CallbackQueryHandler(handle_source_remove_edit, pattern="^(remove_source__|edit_source__).+"),
                CallbackQueryHandler(handle_dest_remove_edit, pattern="^(remove_dest__|edit_dest__).+"),
                CallbackQueryHandler(go_back, pattern="^back_to_start$"),
            ],
            ADD_SOURCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_received)
            ],
            ADD_DESTINATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_destination_received)
            ],
            VIEW_SOURCE_LIST: [
                CallbackQueryHandler(destination_list, pattern="^destination_list$"),
                CallbackQueryHandler(add_destination_start, pattern="^add_destination$"),
                CallbackQueryHandler(toggle_forward, pattern="^toggle_forward$"),
                CallbackQueryHandler(status, pattern="^status$"),
                CallbackQueryHandler(handle_source_remove_edit, pattern="^(remove_source__|edit_source__).+"),
                CallbackQueryHandler(go_back, pattern="^main_menu$"),
            ],
            VIEW_DEST_LIST: [
                CallbackQueryHandler(source_list, pattern="^source_list$"),
                CallbackQueryHandler(add_source_start, pattern="^add_source$"),
                CallbackQueryHandler(toggle_forward, pattern="^toggle_forward$"),
                CallbackQueryHandler(status, pattern="^status$"),
                CallbackQueryHandler(handle_dest_remove_edit, pattern="^(remove_dest__|edit_dest__).+"),
                CallbackQueryHandler(go_back, pattern="^main_menu$"),
            ],
            EDIT_SOURCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_source_received)
            ],
            EDIT_DESTINATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_dest_received)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )
    app.add_handler(conv_handler)
    print("ForwardBot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

