import discord
import os
from dotenv import load_dotenv
import asyncio
from threading import Thread
from flask import Flask
import sys
import importlib

# Load environment variables from .env file
load_dotenv()

# Define Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

# --- Ticket Channel Management ---

# Configuration for support roles (add these role names to your server)
SUPPORT_ROLES = {
    'general': ['Team', 'Supporter', 'Mod'],  # Multiple roles for general support (including Mods)
    'report': 'Mod',                          # Role name for user reports
    'unban': 'Admin'                          # Role name for unban requests
}

# High-level roles that always have access to all tickets
ADMIN_ROLES = ['OWNER', 'Admin']  # These roles always have access to all tickets

# Category ID where ticket channels will be created (set this to your ticket category ID)
TICKET_CATEGORY_ID = None  # Replace with your category ID (int) or leave None for no category

async def has_existing_ticket(guild, user, ticket_type):
    """Checks if user already has an open ticket of this type."""
    # Check for any ticket channel that contains the user's name and ticket type
    user_name_lower = user.name.lower().replace(" ", "-")
    
    for channel in guild.text_channels:
        channel_name_lower = channel.name.lower()
        
        # Check if this is a ticket channel for this user and type
        if (f"ticket-{ticket_type}" in channel_name_lower and 
            user_name_lower in channel_name_lower):
            return channel
            
        # Also check for any ticket channel with this user's name (more flexible)
        if (channel_name_lower.startswith("ticket-") and 
            user_name_lower in channel_name_lower and
            ticket_type.split("-")[0] in channel_name_lower):
            return channel
    
    return None

async def has_any_existing_ticket(guild, user):
    """Checks if user already has any open ticket."""
    user_name_lower = user.name.lower().replace(" ", "-")
    user_id = str(user.id)
    
    print(f"Checking tickets for user: {user.name} (ID: {user_id})")  # Debug
    
    for channel in guild.text_channels:
        channel_name_lower = channel.name.lower()
        
        print(f"Checking channel: {channel_name_lower}")  # Debug
        
        # Check multiple patterns for ticket channels
        if channel_name_lower.startswith("ticket-"):
            # Pattern 1: ticket-type-username
            if user_name_lower in channel_name_lower:
                print(f"Found existing ticket by username: {channel.name}")  # Debug
                return channel
            
            # Pattern 2: ticket-type-userid
            if user_id in channel_name_lower:
                print(f"Found existing ticket by user ID: {channel.name}")  # Debug
                return channel
            
            # Pattern 3: Check channel permissions (most reliable)
            # If user has specific permissions in a ticket channel, it's likely their ticket
            overwrites = channel.overwrites_for(user)
            if overwrites.read_messages is True and overwrites.send_messages is not None:
                # Check if this looks like a ticket channel for this user
                if any(word in channel_name_lower for word in ["ticket", "support", "report", "unban"]):
                    print(f"Found existing ticket by permissions: {channel.name}")  # Debug
                    return channel
    
    print("No existing tickets found")  # Debug
    return None

async def create_ticket_channel(guild, user, ticket_type, support_role_names):
    """Creates a private ticket channel for the user."""
    
    # Set channel permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),  # Hide from everyone
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),  # User can read/write
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)  # Bot can read/write
    }
    
    # Add admin roles (OWNER, Admin) - they always have access to all tickets
    for admin_role_name in ADMIN_ROLES:
        admin_role = discord.utils.get(guild.roles, name=admin_role_name)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
    
    # Add specific support role permissions
    # Handle both single role (string) and multiple roles (list)
    if isinstance(support_role_names, str):
        support_role_names = [support_role_names]
    
    for role_name in support_role_names:
        support_role = discord.utils.get(guild.roles, name=role_name)
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    
    # Get category if specified
    category = None
    if TICKET_CATEGORY_ID:
        category = guild.get_channel(TICKET_CATEGORY_ID)
    
    # Create the channel WITHOUT user ID in name
    channel_name = f"ticket-{ticket_type}-{user.name}".lower().replace(" ", "-")
    channel = await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites,
        category=category,
        topic=f"Support Ticket für {user.display_name} (ID: {user.id}) - {ticket_type}"
    )
    
    print(f"Created ticket channel: {channel.name} for user {user.name} (ID: {user.id})")  # Debug
    return channel

class TicketCloseView(discord.ui.View):
    """View with close and delete buttons for ticket channels."""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🔒 Ticket schließen", style=discord.ButtonStyle.secondary, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check permissions for closing tickets
            allowed = False
            user_roles = [role.name for role in interaction.user.roles]
            
            # Check if user has admin roles (OWNER, Admin) - they can always close
            for admin_role in ADMIN_ROLES:
                if admin_role in user_roles:
                    allowed = True
                    break
            
            # Check if user has any support role
            if not allowed:
                for ticket_type, support_roles in SUPPORT_ROLES.items():
                    # Handle both single role (string) and multiple roles (list)
                    if isinstance(support_roles, str):
                        support_roles = [support_roles]
                    
                    for support_role in support_roles:
                        if support_role in user_roles:
                            allowed = True
                            break
                    if allowed:
                        break
            
            # Check if user is the ticket creator - MORE RELIABLE CHECK
            is_ticket_creator = False
            
            # Method 1: Check channel name
            if interaction.user.name.lower() in interaction.channel.name.lower():
                is_ticket_creator = True
            
            # Method 2: Check channel topic for user ID
            if interaction.channel.topic and str(interaction.user.id) in interaction.channel.topic:
                is_ticket_creator = True
            
            # Method 3: Check channel permissions
            user_perms = interaction.channel.overwrites_for(interaction.user)
            if user_perms.read_messages is True and user_perms.send_messages is True:
                is_ticket_creator = True
            
            if not allowed and is_ticket_creator:
                allowed = True
            
            if not allowed:
                await interaction.response.send_message("❌ Du hast keine Berechtigung, dieses Ticket zu schließen!", ephemeral=True)
                return
            
            # Close ticket (remove write permissions for ticket creator)
            embed = discord.Embed(
                title="🔒 Ticket geschlossen",
                description=f"Dieses Ticket wurde von {interaction.user.mention} geschlossen.\n\nDas Ticket kann mit dem 🗑️ Button gelöscht werden.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
            
            # Remove write permissions for the ticket creator if they exist
            overwrites = interaction.channel.overwrites
            for user_or_role, perms in overwrites.items():
                if isinstance(user_or_role, discord.Member) and user_or_role != interaction.guild.me:
                    # Check if this is likely the ticket creator
                    if (user_or_role.name.lower() in interaction.channel.name.lower() or 
                        (interaction.channel.topic and str(user_or_role.id) in interaction.channel.topic)):
                        overwrites[user_or_role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
            
            await interaction.channel.edit(overwrites=overwrites)
            
        except Exception as e:
            print(f"Error in close_ticket: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Fehler beim Schließen des Tickets. Versuche es erneut.", ephemeral=True)

    @discord.ui.button(label="🗑️ Ticket löschen", style=discord.ButtonStyle.red, custom_id="delete_ticket")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user is the ticket creator - they CANNOT delete
            is_ticket_creator = False
            
            # Method 1: Check channel name
            if interaction.user.name.lower() in interaction.channel.name.lower():
                is_ticket_creator = True
            
            # Method 2: Check channel topic for user ID
            if interaction.channel.topic and str(interaction.user.id) in interaction.channel.topic:
                is_ticket_creator = True
            
            # Method 3: Check if user has specific ticket creator permissions
            user_perms = interaction.channel.overwrites_for(interaction.user)
            if (user_perms.read_messages is True and user_perms.send_messages is not None and 
                not any(role.name in [role for roles in SUPPORT_ROLES.values() for role in (roles if isinstance(roles, list) else [roles])] + ADMIN_ROLES for role in interaction.user.roles)):
                is_ticket_creator = True
            
            # Ticket creator cannot delete
            if is_ticket_creator:
                await interaction.response.send_message("❌ Als Ticket-Ersteller kannst du das Ticket nicht löschen! Nur Support-Rollen und Admins können Tickets löschen.", ephemeral=True)
                return
            
            # Check if user has permission to delete (all roles that have access to the ticket)
            allowed = False
            user_roles = [role.name for role in interaction.user.roles]
            
            # Check if user has admin roles (OWNER, Admin) - they are pinged in all tickets
            for admin_role in ADMIN_ROLES:
                if admin_role in user_roles:
                    allowed = True
                    break
            
            # Check if user has any support role that gets pinged in tickets
            if not allowed:
                for ticket_type, support_roles in SUPPORT_ROLES.items():
                    # Handle both single role (string) and multiple roles (list)
                    if isinstance(support_roles, str):
                        support_roles = [support_roles]
                    
                    for support_role in support_roles:
                        if support_role in user_roles:
                            allowed = True
                            break
                    if allowed:
                        break
            
            if not allowed:
                await interaction.response.send_message("❌ Du hast keine Berechtigung, Tickets zu löschen! Nur gepingte Rollen (Support-Teams und Admins) können Tickets löschen.", ephemeral=True)
                return
            
            # Delete the ticket
            await interaction.response.send_message("🗑️ Ticket wird in 5 Sekunden gelöscht...", ephemeral=False)
            await asyncio.sleep(5)
            await interaction.channel.delete(reason=f"Ticket gelöscht von {interaction.user}")
            
        except Exception as e:
            print(f"Error in delete_ticket: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Fehler beim Löschen des Tickets. Versuche es erneut.", ephemeral=True)

# --- Discord UI Components (Buttons) ---

# Define a View for the buttons
class TicketSystemView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Keep the view persistent

    @discord.ui.button(label="General Support", style=discord.ButtonStyle.blurple, emoji="🛠️", custom_id="general_support")
    async def general_support_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user already has ANY ticket (not just general support)
            existing_ticket = await has_any_existing_ticket(interaction.guild, interaction.user)
            if existing_ticket:
                await interaction.response.send_message(
                    f"❌ Du hast bereits ein offenes Ticket: {existing_ticket.mention}\n"
                    f"Bitte schließe dein aktuelles Ticket, bevor du ein neues erstellst.", 
                    ephemeral=True
                )
                return
            
            # Create ticket channel
            channel = await create_ticket_channel(
                interaction.guild, 
                interaction.user, 
                "general-support", 
                SUPPORT_ROLES['general']
            )
            
            await interaction.response.send_message(f"🛠️ General Support Ticket erstellt: {channel.mention}", ephemeral=True)
            
            # Send welcome message in the new channel
            embed = discord.Embed(
                title="🛠️ General Support Ticket",
                description=f"Hallo {interaction.user.mention}!\n\nBeschreibe dein Problem so detailliert wie möglich. Ein Support-Mitarbeiter wird dir bald helfen.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Ticket erstellt von", value=interaction.user.display_name, inline=True)
            embed.add_field(name="Kategorie", value="General Support", inline=True)
            
            # Smart mention system based on roles and ticket type
            mentions = [interaction.user.mention]
            
            # Always mention admin roles (OWNER, Admin) - they get pinged for all tickets
            for admin_role_name in ADMIN_ROLES:
                admin_role = discord.utils.get(interaction.guild.roles, name=admin_role_name)
                if admin_role:
                    mentions.append(admin_role.mention)
            
            # Mention specific support roles for this ticket type
            support_roles = SUPPORT_ROLES['general']
            if isinstance(support_roles, str):
                support_roles = [support_roles]
            
            for role_name in support_roles:
                support_role = discord.utils.get(interaction.guild.roles, name=role_name)
                if support_role:
                    mentions.append(support_role.mention)
            
            mention_text = " ".join(mentions)
            await channel.send(mention_text, embed=embed, view=TicketCloseView())
            
        except Exception as e:
            print(f"Error in general_support_button: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Fehler beim Erstellen des Tickets. Versuche es erneut.", ephemeral=True)

    @discord.ui.button(label="Report User", style=discord.ButtonStyle.red, emoji="⚠️", custom_id="report_user")
    async def report_user_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user already has ANY ticket (not just user report)
            existing_ticket = await has_any_existing_ticket(interaction.guild, interaction.user)
            if existing_ticket:
                await interaction.response.send_message(
                    f"❌ Du hast bereits ein offenes Ticket: {existing_ticket.mention}\n"
                    f"Bitte schließe dein aktuelles Ticket, bevor du ein neues erstellst.", 
                    ephemeral=True
                )
                return
            
            # Create ticket channel
            channel = await create_ticket_channel(
                interaction.guild, 
                interaction.user, 
                "user-report", 
                SUPPORT_ROLES['report']
            )
            
            await interaction.response.send_message(f"⚠️ User Report Ticket erstellt: {channel.mention}", ephemeral=True)
            
            # Send welcome message in the new channel
            embed = discord.Embed(
                title="⚠️ User Report Ticket",
                description=f"Hallo {interaction.user.mention}!\n\nBitte gib folgende Informationen an:\n• **Gemeldeter User:** (Name/ID)\n• **Grund der Meldung:**\n• **Beweise:** (Screenshots, Links, etc.)",
                color=discord.Color.red()
            )
            embed.add_field(name="Ticket erstellt von", value=interaction.user.display_name, inline=True)
            embed.add_field(name="Kategorie", value="User Report", inline=True)
            
            # Smart mention system based on roles and ticket type
            mentions = [interaction.user.mention]
            
            # Always mention admin roles (OWNER, Admin) - they get pinged for all tickets
            for admin_role_name in ADMIN_ROLES:
                admin_role = discord.utils.get(interaction.guild.roles, name=admin_role_name)
                if admin_role:
                    mentions.append(admin_role.mention)
            
            # Mention specific support role for user reports
            support_role = discord.utils.get(interaction.guild.roles, name=SUPPORT_ROLES['report'])
            if support_role:
                mentions.append(support_role.mention)
            
            mention_text = " ".join(mentions)
            await channel.send(mention_text, embed=embed, view=TicketCloseView())
            
        except Exception as e:
            print(f"Error in report_user_button: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Fehler beim Erstellen des Tickets. Versuche es erneut.", ephemeral=True)

    @discord.ui.button(label="Unban Antrag", style=discord.ButtonStyle.green, emoji="🔓", custom_id="unban_request")
    async def unban_request_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user already has ANY ticket (not just unban request)
            existing_ticket = await has_any_existing_ticket(interaction.guild, interaction.user)
            if existing_ticket:
                await interaction.response.send_message(
                    f"❌ Du hast bereits ein offenes Ticket: {existing_ticket.mention}\n"
                    f"Bitte schließe dein aktuelles Ticket, bevor du ein neues erstellst.", 
                    ephemeral=True
                )
                return
            
            # Create ticket channel
            channel = await create_ticket_channel(
                interaction.guild, 
                interaction.user, 
                "unban-antrag", 
                SUPPORT_ROLES['unban']
            )
            
            await interaction.response.send_message(f"🔓 Unban Antrag erstellt: {channel.mention}", ephemeral=True)
            
            # Send welcome message in the new channel
            embed = discord.Embed(
                title="🔓 Unban Antrag Ticket",
                description=f"Hallo {interaction.user.mention}!\n\nBitte fülle folgende Informationen aus:\n• **Gebannter Account:** (Name/ID)\n• **Grund des Banns:**\n• **Warum solltest du entbannt werden:**\n• **Wirst du die Regeln befolgen:**",
                color=discord.Color.green()
            )
            embed.add_field(name="Ticket erstellt von", value=interaction.user.display_name, inline=True)
            embed.add_field(name="Kategorie", value="Unban Antrag", inline=True)
            
            # Smart mention system based on roles and ticket type
            mentions = [interaction.user.mention]
            
            # Always mention admin roles (OWNER, Admin) - they get pinged for all tickets
            for admin_role_name in ADMIN_ROLES:
                admin_role = discord.utils.get(interaction.guild.roles, name=admin_role_name)
                if admin_role:
                    mentions.append(admin_role.mention)
            
            # Mention specific support role for unban requests
            support_role = discord.utils.get(interaction.guild.roles, name=SUPPORT_ROLES['unban'])
            if support_role:
                mentions.append(support_role.mention)
            
            mention_text = " ".join(mentions)
            await channel.send(mention_text, embed=embed, view=TicketCloseView())
            
        except Exception as e:
            print(f"Error in unban_request_button: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Fehler beim Erstellen des Tickets. Versuche es erneut.", ephemeral=True)

# --- Reload function ---
async def reload_bot():
    """Reloads the bot by restarting the Python process."""
    print("Bot wird neu geladen...")
    await client.close()
    
    # Restart the Python process
    os.execv(sys.executable, ['python'] + sys.argv)

# --- Discord Bot Events and Commands ---

@client.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f'{client.user} has successfully logged in!')
    await client.change_presence(activity=discord.Game(name="mit Python"))

    # Add the persistent views when the bot starts
    # This is crucial for buttons to work after a bot restart
    try:
        client.add_view(TicketSystemView())
        client.add_view(TicketCloseView())
        print("Persistent Views loaded successfully!")
    except Exception as e:
        print(f"Error loading persistent views: {e}")


@client.event
async def on_interaction(interaction):
    """Handle interactions that might fail."""
    try:
        # Let the normal interaction handling proceed
        pass
    except Exception as e:
        print(f"Interaction error: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Ein Fehler ist aufgetreten. Versuche es erneut oder kontaktiere einen Admin.", ephemeral=True)


@client.event
async def on_message(message):
    """Called when a message is received in a channel the bot can see."""
    if message.author == client.user:
        return

    # Basic example commands
    if message.content.startswith('!hallo'):
        await message.delete()  # Delete command message
        await message.channel.send('Hallo!', delete_after=5)  # Auto-delete after 5 seconds
    elif message.content.startswith('!ping'):
        await message.delete()  # Delete command message
        await message.channel.send('Pong!', delete_after=5)  # Auto-delete after 5 seconds
    elif message.content.startswith('!info'):
        await message.delete()  # Delete command message
        await message.channel.send(f'I am a Discord bot, created by {message.author.display_name}.', delete_after=5)

    # Clear command to delete messages
    elif message.content.startswith('!clear'):
        # Check if user has manage messages permission
        if not message.author.guild_permissions.manage_messages:
            # Send ephemeral-like message by DMing the user
            try:
                await message.author.send("❌ Du hast keine Berechtigung für diesen Befehl!")
            except:
                # If DM fails, send in channel but delete quickly
                error_msg = await message.channel.send("❌ Du hast keine Berechtigung für diesen Befehl!")
                await asyncio.sleep(3)
                await error_msg.delete()
            await message.delete()
            return
        
        # Parse the number of messages to delete
        try:
            # Split the command to get the number
            parts = message.content.split()
            if len(parts) > 1:
                amount = int(parts[1])
                if amount > 100:
                    amount = 100  # Discord limit
                elif amount < 1:
                    amount = 1
            else:
                amount = 1  # Default to 1 if no number specified
        except ValueError:
            try:
                await message.author.send("❌ Bitte gib eine gültige Zahl an! Beispiel: `!clear 10`")
            except:
                error_msg = await message.channel.send("❌ Bitte gib eine gültige Zahl an! Beispiel: `!clear 10`")
                await asyncio.sleep(3)
                await error_msg.delete()
            await message.delete()
            return
        
        # Delete the command message first
        await message.delete()
        
        # Delete the specified number of messages
        deleted_messages = await message.channel.purge(limit=amount)
        
        # Send success message
        embed = discord.Embed(
            title="✅ Aktion erfolgreich!",
            description=f"Somit hast du {len(deleted_messages)} Nachrichten aus diesem Kanal gelöscht.",
            color=discord.Color.green()
        )
        embed.set_footer(text="GalaxyBot", icon_url=client.user.avatar.url if client.user.avatar else None)
        
        # Send the embed and delete it after 5 seconds
        success_msg = await message.channel.send(embed=embed)
        await asyncio.sleep(5)
        await success_msg.delete()

    # Reload command - nur für Administratoren/Owner
    elif message.content.startswith('!reload'):
        # Überprüfe, ob der Benutzer Berechtigung hat (z.B. Administrator oder Bot Owner)
        if message.author.guild_permissions.administrator or message.author.id == int(os.getenv('BOT_OWNER_ID', '0')):
            await message.delete()  # Delete command message
            reload_msg = await message.channel.send("🔄 Bot wird neu geladen...")
            await asyncio.sleep(2)
            await reload_msg.delete()
            await reload_bot()
        else:
            try:
                await message.author.send("❌ Du hast keine Berechtigung für diesen Befehl!")
            except:
                error_msg = await message.channel.send("❌ Du hast keine Berechtigung für diesen Befehl!")
                await asyncio.sleep(3)
                await error_msg.delete()
            await message.delete()

    # New command to send the Ticket System message with buttons (Admin only)
    elif message.content.startswith('!ticketsystem'):
        # Check if user has admin permissions
        if not (message.author.guild_permissions.administrator or message.author.id == int(os.getenv('BOT_OWNER_ID', '0'))):
            try:
                await message.author.send("❌ Du hast keine Berechtigung für diesen Befehl! Nur Administratoren können das Ticket-System erstellen.")
            except:
                error_msg = await message.channel.send("❌ Du hast keine Berechtigung für diesen Befehl! Nur Administratoren können das Ticket-System erstellen.")
                await asyncio.sleep(3)
                await error_msg.delete()
            await message.delete()
            return
        
        # Create the Embed
        embed = discord.Embed(
            title="Server_Name TICKETSYSTEM ✉️",
            description=(
                "Wähle die passende Kategorie für dein Anliegen:\n\n"
                "🛠️ **General Support**\n"
                "Hilfe bei allgemeinen Fragen\n\n"
                "⚠️ **Report User**\n"
                "Melde Regelverstöße\n\n"
                "🔓 **Unban Antrag**\n"
                "Stelle einen Antrag auf Entbannung\n\n"
                "Klicke auf einen Button, um zu starten."
            ),
            color=discord.Color.blue() # You can choose any color
        )

        # Send the message with the Embed and the View (buttons)
        await message.channel.send(embed=embed, view=TicketSystemView())
        await message.delete() # Optional: delete the command message to keep the channel clean

# --- Functions for 24/7 operation (via hosting services) ---

app = Flask(__name__)

@app.route('/')
def home():
    """Home page of the Flask app, simply to confirm that the app is running."""
    return "I am alive!"

def run_flask():
    """Starts the Flask web server in a separate thread."""
    # Try to get port from Pterodactyl environment variables
    port_nenne = int(os.getenv('SERVER_PORT', os.getenv('PORT', os.getenv('PTERODACTYL_PORT', 25591))))
    print(f"Flask server starting on port: {port_nenne}")
    app.run(host='0.0.0.0', port=port_nenne)

def run_discord_bot():
    """Starts the Discord bot with the stored token."""
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
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    run_discord_bot()
