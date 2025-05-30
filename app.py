import discord
import os
from dotenv import load_dotenv
import asyncio
from threading import Thread

# Lade Umgebungsvariablen aus .env Datei
load_dotenv()

# Discord Intentions definieren
# WICHTIG: Aktiviere die notwendigen Intents in deinen Discord Developer Portal!
# Für diesen Bot sind 'message_content' und 'members' (für GuildMessages) wahrscheinlich notwendig.
intents = discord.Intents.default()
intents.message_content = True  # Erlaubt dem Bot, den Inhalt von Nachrichten zu lesen
intents.members = True # Erlaubt dem Bot, Informationen über Mitglieder zu erhalten (falls benötigt)

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'{client.user} hat sich erfolgreich angemeldet!')
    # Setzt den Status des Bots
    await client.change_presence(activity=discord.Game(name="mit Python"))

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!hallo'):
        await message.channel.send('Hallo!')
    elif message.content.startswith('!ping'):
        await message.channel.send('Pong!')
    elif message.content.startswith('!info'):
        await message.channel.send(f'Ich bin ein Discord-Bot, erstellt von {message.author.display_name}.')

# Funktion, die den Bot startet
def run_bot():
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    if DISCORD_TOKEN is None:
        print("Fehler: DISCORD_TOKEN nicht gefunden. Bitte stelle sicher, dass du eine .env-Datei mit DISCORD_TOKEN='DEIN_BOT_TOKEN' hast.")
        return
    try:
        client.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("Fehler: Ungültiger Bot-Token. Bitte überprüfe deinen DISCORD_TOKEN in der .env-Datei.")
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")

# Um den Bot 24/7 am Laufen zu halten, ist ein Hostingservice erforderlich.
# Die folgende `keep_alive` Funktion und das Flask/Webserver-Setup
# sind primär für Services wie Replit gedacht, die einen Webserver benötigen,
# um am Leben gehalten zu werden. Für andere Hosting-Dienste (z.B. VPS, Heroku)
# ist dies oft nicht notwendig.
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Ich bin am Leben!"

def run_flask():
    app.run(host='0.0.0.0', port=os.getenv('PORT', 8080))

if __name__ == '__main__':
    # Starte Flask in einem separaten Thread
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Starte den Discord-Bot
    run_bot()
