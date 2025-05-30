import discord
import os
from dotenv import load_dotenv
import asyncio
from threading import Thread
from flask import Flask

# Load environment variables from .env file
# Make sure you have a .env file in the same directory containing your bot token:
# DISCORD_TOKEN=YOUR_BOT_TOKEN
load_dotenv()

# Define Discord Intents
# IMPORTANT: Enable the necessary Intents in your Discord Developer Portal!
# For this bot, 'message_content' and 'members' (for GuildMessages) are likely needed.
intents = discord.Intents.default()
intents.message_content = True  # Allows the bot to read message content
intents.members = True # Allows the bot to get information about members (if needed)

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f'{client.user} has successfully logged in!')
    # Set the bot's status in Discord
    await client.change_presence(activity=discord.Game(name="with Python"))

@client.event
async def on_message(message):
    """Called when a message is received in a channel the bot can see."""
    # Ignore messages from the bot itself to prevent infinite loops
    if message.author == client.user:
        return

    # Example commands
    if message.content.startswith('!hallo'):
        await message.channel.send('Hallo!')
    elif message.content.startswith('!ping'):
        await message.channel.send('Pong!')
    elif message.content.startswith('!info'):
        await message.channel.send(f'I am a Discord bot, created by {message.author.display_name}.')

# --- Functions for 24/7 operation (via hosting services) ---

# Flask app for status monitoring by hosting services
app = Flask(__name__)

@app.route('/')
def home():
    """Home page of the Flask app, simply to confirm that the app is running."""
    return "I am alive!"

def run_flask():
    """Starts the Flask web server in a separate thread."""
    # The port is often set by hosting services via environment variables
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Function that starts the Discord bot
def run_discord_bot():
    """Starts the Discord bot with the stored token."""
    # This line correctly loads the token from the environment variable (e.g., from .env file)
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    if DISCORD_TOKEN is None:
        print("Error: DISCORD_TOKEN not found. Please ensure you have a .env file with DISCORD_TOKEN='YOUR_BOT_TOKEN' in the same directory.")
        return
    try:
        client.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("Error: Invalid bot token. Please check your DISCORD_TOKEN in the .env file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    # Start the Flask web server in a separate thread.
    # This is important for hosting services like Replit, which expect a web server
    # to recognize the application as "active" and keep it running.
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Start the Discord bot.
    # The bot runs in the main thread.
    run_discord_bot()
