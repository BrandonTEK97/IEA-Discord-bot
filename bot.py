import os
import time
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
        pass

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
    if message.author == client.user:
        return
    
    if not isinstance(message.channel, discord.DMChannel):
        return
    
    print(f"Received DM from {message.author}: {message.content}")
    
    async with message.channel.typing():
        try:
            # Create a session using the correct Managed Agents API
            session = anthropic_client.beta.sessions.create(
                agent={"type": "agent", "id": AGENT_ID},
                environment_id=ENVIRONMENT_ID,
            )
            
            # Send user message as an event
            anthropic_client.beta.sessions.events.send(
                session_id=session.id,
                events=[
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": message.content}],
                    }
                ],
            )
            
            # Stream the response
            reply = ""
            with anthropic_client.beta.sessions.stream(
                session_id=session.id,
            ) as stream:
                for event in stream:
                    if event.type == "agent.message":
                        for block in event.content:
                            if hasattr(block, 'text'):
                                reply += block.text
                    elif event.type == "session.status_terminated":
                        break
                    elif event.type == "session.status_idle":
                        break
            
            # Send response back to Discord
            if not reply:
                reply = "I processed your request but had no text response."
            
            if len(reply) > 2000:
                chunks = [reply[i:i+2000] for i in range(0, len(reply), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(reply)
            
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send(f"Sorry, I encountered an error: {str(e)[:200]}")

# Start health check server
Thread(target=run_health_server, daemon=True).start()

# Run the Discord bot
client.run(os.environ.get("DISCORD_BOT_TOKEN"))
