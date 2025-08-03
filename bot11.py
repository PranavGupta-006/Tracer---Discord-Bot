
import os

def get_bot_folder():
    home = os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    bot_folder = os.path.join(desktop, "bot")

    if not os.path.exists(bot_folder):
        os.makedirs(bot_folder)
    
    return bot_folder

UPLOAD_FOLDER = get_bot_folder()
import os
import sqlite3
import uuid
import datetime
from cryptography.fernet import Fernet
import discord
from discord.ext import commands


UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ENCRYPTION_KEY = Fernet.generate_key()
cipher = Fernet(ENCRYPTION_KEY)

def get_db_for_guild(guild_id):
    db_path = f"guild_{guild_id}.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contact_details (
        item_id TEXT PRIMARY KEY,
        item_name TEXT,
        encrypted_owner_details BLOB,
        encrypted_finder_details BLOB,
        description TEXT,
        upload_date TEXT,
        image_path TEXT
    )
    """)
    conn.commit()
    return conn, cursor

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("✅ The Bot is up and awaits commands! Use `!info` to view all commands.")

@bot.command(name="info")
async def info(ctx):
    response = """
**Available Commands:**
- `!ping`: Check if the bot is active.
- `!upload <item_name>`: Upload an image of an item.
- `!delete-images <item_id>`: Delete the image associated with the specified item ID.
- `!find <item_name>`: Find all items with a name that matches or contains the given name.
"""
    await ctx.send(response)

@bot.command(name="upload")
async def upload(ctx, item_name: str = None):
    if not item_name:
        await ctx.send("❓ **Please provide an item name:**")

        def check_name(msg):
            return msg.author == ctx.author

        try:
            msg = await bot.wait_for("message", check=check_name, timeout=60.0)
            item_name = msg.content
        except Exception:
            await ctx.send("⚠️ Item name not provided. Upload canceled.")
            return

    conn, cursor = get_db_for_guild(ctx.guild.id)
    item_name = item_name.replace(" ", "_") 

    item_id = str(uuid.uuid4())
    date_folder = datetime.datetime.now().strftime("%Y-%m-%d")
    item_folder = os.path.join(UPLOAD_DIR, date_folder, item_id)
    os.makedirs(item_folder, exist_ok=True)

    await ctx.send(f"📝 **Instructions:** Please upload the image for the item '{item_name}' now.\nYour unique item ID is `{item_id}`.")

    def check(msg):
        return msg.author == ctx.author and msg.attachments

    try:
        msg = await bot.wait_for("message", check=check, timeout=60.0)
        attachment = msg.attachments[0]
        file_path = os.path.join(item_folder, attachment.filename)
        await attachment.save(file_path)

        upload_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO contact_details (item_id, item_name, upload_date, image_path)
        VALUES (?, ?, ?, ?)
        """, (item_id, item_name, upload_date, file_path))
        conn.commit()

        await ctx.send(f"✅ Image saved for item '{item_name}' under ID `{item_id}` (Click to Copy).")

        await ctx.send(f"🔹 **Please provide the contact details of the finder for item `{item_name}`:**")

        def check_finder(msg):
            return msg.author == ctx.author

        try:
            finder_msg = await bot.wait_for("message", check=check_finder, timeout=60.0)
            finder_details = finder_msg.content
            encrypted_finder_details = cipher.encrypt(finder_details.encode())
            cursor.execute("""
            UPDATE contact_details SET encrypted_finder_details = ?
            WHERE item_id = ?
            """, (encrypted_finder_details, item_id))
            conn.commit()
            await ctx.send(f"✅ Finder details stored for item ID `{item_id}`.")
        except Exception:
            await ctx.send("⚠️ Finder details were not provided or an error occurred.")


        await ctx.send(f"🔹 **Please provide a description for item `{item_name}`:**")

        try:
            description_msg = await bot.wait_for("message", check=check_finder, timeout=60.0)
            description = description_msg.content
            cursor.execute("""
            UPDATE contact_details SET description = ?
            WHERE item_id = ?
            """, (description, item_id))
            conn.commit()
            await ctx.send(f"✅ Description stored for item ID `{item_id}`.")
        except Exception:
            await ctx.send("⚠️ Description was not provided or an error occurred.")
        
    except Exception as e:
        await ctx.send(f"⚠️ An error occurred while uploading: {e}")


@bot.command(name="store-owner-details")
async def store_owner_details(ctx, item_name: str, contact_details: str):
    if not ctx.guild:
        await ctx.send("⚠️ This command can only be used in a server.")
        return

    conn, cursor = get_db_for_guild(ctx.guild.id)
    item_id = str(uuid.uuid4())
    encrypted_details = cipher.encrypt(contact_details.encode())
    cursor.execute("""
    INSERT INTO contact_details (item_id, item_name, encrypted_owner_details)
    VALUES (?, ?, ?)
    """, (item_id, item_name, encrypted_details))
    conn.commit()
    await ctx.send(f"✅ Owner contact details for '{item_name}' have been stored with ID `{item_id}`.")

@bot.command(name="store-finder-details")
async def store_finder_details(ctx, item_id: str, contact_details: str):
    if not ctx.guild:
        await ctx.send("⚠️ This command can only be used in a server.")
        return

    conn, cursor = get_db_for_guild(ctx.guild.id)
    encrypted_details = cipher.encrypt(contact_details.encode())
    cursor.execute("""
    UPDATE contact_details SET encrypted_finder_details = ?
    WHERE item_id = ?
    """, (encrypted_details, item_id))
    conn.commit()
    await ctx.send(f"✅ Finder contact details stored for item ID `{item_id}`.")

@bot.command(name="show-details")
async def show_details(ctx, item_id: str):
    if not ctx.guild:
        await ctx.send("⚠️ This command can only be used in a server.")
        return

    conn, cursor = get_db_for_guild(ctx.guild.id)
    cursor.execute("SELECT item_name, encrypted_owner_details, encrypted_finder_details FROM contact_details WHERE item_id = ?", (item_id,))
    result = cursor.fetchone()
    if result:
        item_name, encrypted_owner, encrypted_finder = result
        owner_details = cipher.decrypt(encrypted_owner).decode() if encrypted_owner else "Not available"
        finder_details = cipher.decrypt(encrypted_finder).decode() if encrypted_finder else "Not available"
        response = f"**Contact Details for '{item_name}' (ID: `{item_id}`)**\n🔹 Owner: {owner_details}\n🔹 Finder: {finder_details}"
        await ctx.send(response)
    else:
        await ctx.send(f"⚠️ No contact details found for item ID `{item_id}`.")

@bot.command(name="show-image")
async def show_image(ctx, item_id: str):
    if not ctx.guild:
        await ctx.send("⚠️ This command can only be used in a server.")
        return

    conn, cursor = get_db_for_guild(ctx.guild.id)
    cursor.execute("SELECT image_path FROM contact_details WHERE item_id = ?", (item_id,))
    result = cursor.fetchone()

    if result:
        image_path = result[0]
        if os.path.exists(image_path):
            await ctx.send(f"📸 **Here is the image for item ID `{item_id}`:**", file=discord.File(image_path))
        else:
            await ctx.send(f"⚠️ Image file not found for item ID `{item_id}`.")
    else:
        await ctx.send(f"⚠️ No item found with the ID `{item_id}`.")

@bot.command(name="find")
async def find(ctx, item_name: str):
    conn, cursor = get_db_for_guild(ctx.guild.id)

    search_term = f"%{item_name.lower()}%"

    cursor.execute("""
    SELECT item_id, item_name, upload_date, image_path, description, encrypted_finder_details 
    FROM contact_details
    WHERE LOWER(item_name) LIKE ?
    """, (search_term,))
    matches = cursor.fetchall()

    if not matches:
        await ctx.send(f"❌ No items matching '{item_name}' found.")
        return

    for item in matches:
        item_id, name, upload_date, image_path, description, encrypted_finder_details = item

        finder_details = "Not provided"
        if encrypted_finder_details:
            try:
                finder_details = cipher.decrypt(encrypted_finder_details).decode()
            except Exception:
                finder_details = "Error decrypting details"

        description_text = description if description else "No description provided"
        response = (
            f"🔍 **Item Found:** `{name}`\n"
            f"🆔 **Item ID:** `{item_id}`\n"
            f"📅 **Upload Date:** `{upload_date}`\n"
            f"📝 **Description of the item:** {description_text}\n"
            f"📞 **Finder Details:** {finder_details}"
        )

        await ctx.send(response)
        if image_path and os.path.exists(image_path):
            await ctx.send(file=discord.File(image_path))




@bot.command()
async def clear_db(ctx, password: str):
    """
    Clears all records from the lost and found database and deletes stored images if the correct password is provided.
    """
    if password != "ClearDB":
        await ctx.send("❌ Incorrect password. Database not cleared.")
        return

    conn, cursor = get_db_for_guild(ctx.guild.id)
    if not conn:
        await ctx.send("⚠️ Database connection error. Please try again.")
        return

    try:
        cursor.execute("DELETE FROM items")
        conn.commit()

        upload_dir = "uploads"
        if os.path.exists(upload_dir):
            for filename in os.listdir(upload_dir):
                file_path = os.path.join(upload_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)

        await ctx.send("✅ Database and images successfully cleared.")
    except Exception as e:
        await ctx.send(f"⚠️ An error occurred while clearing the database: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def remove_empty_folders(directory="./uploads"):
    """
    Recursively removes empty folders inside the given directory.
    """
    for folder in os.listdir(directory):
        folder_path = os.path.join(directory, folder)
        if os.path.isdir(folder_path):
            remove_empty_folders(folder_path)
            if not os.listdir(folder_path): 
                os.rmdir(folder_path)
                print(f"Deleted empty folder: {folder_path}")



TOKEN = os.getenv("DISCORD_BOT_TOKEN", "INSERT_SERVER_TOKEN_HERE!!!!")  
bot.run(TOKEN)
