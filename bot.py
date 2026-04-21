import os
import discord
from anthropic import Anthropic
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Initialize Discord client
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=os.environ.get("CLAUDE_API_KEY"))
AGENT_ID = os.environ.get("AGENT_ID")
ENVIRONMENT_ID = os.environ.get("ENVIRONMENT_ID", "academy-admin-env")

# Simple HTTP server for Render health checks
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')
    
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f'Health check server running on port {port}')
    server.serve_forever()

@client.event
async def on_ready():
    print(f'{client.user} is now online and ready!')

@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return
    
    # Only respond to DMs
    if not isinstance(message.channel, discord.DMChannel):
        return
    
    print(f"Received DM from {message.author}: {message.content}")
    
    # Show typing indicator
    async with message.channel.typing():
        try:
            # Create agent session with message
            session = anthropic_client.beta.managed_agent.sessions.create(
                agent_id=AGENT_ID,
                environment_id=ENVIRONMENT_ID
            )
            
            # Send message to agent
            response = anthropic_client.beta.managed_agent.sessions.messages.create(
                session_id=session.id,
                content=message.content
            )
            
            # Extract text response
            reply = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    reply += block.text
            
            # Send response back to Discord (split if too long)
            if len(reply) > 2000:
                # Discord has 2000 char limit, split message
                chunks = [reply[i:i+2000] for i in range(0, len(reply), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(reply or "I processed your request!")
            
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send(f"Sorry, I encountered an error: {str(e)[:100]}")

# Start health check server in background thread
Thread(target=run_health_server, daemon=True).start()

# Run the Discord bot
client.run(os.environ.get("DISCORD_BOT_TOKEN"))
