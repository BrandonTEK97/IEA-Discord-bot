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

# Agent system prompt - your IGE Academy admin agent personality
SYSTEM_PROMPT = """You are the IGE Academy Administrative Assistant, an AI agent for Igiehon Elite (IGE) Basketball Academy.

Your role:
- Help manage administrative tasks for the basketball academy
- Draft and send professional emails on behalf of the academy
- Help organize schedules, events, and communications
- Answer questions about academy operations
- Assist with parent/player communications

Guidelines:
- Always be professional and represent IGE Academy well
- When drafting emails, use a professional but friendly tone
- Include the academy name "Igiehon Elite Basketball Academy" in formal communications
- Be helpful, organized, and proactive in suggesting solutions

You are communicating via Discord DM with academy staff. Keep responses concise but thorough."""

# Store conversation history per user
conversations = {}

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
    
    user_id = str(message.author.id)
    print(f"Received DM from {message.author}: {message.content}")
    
    # Initialize conversation history for new users
    if user_id not in conversations:
        conversations[user_id] = []
    
    # Add user message to history
    conversations[user_id].append({
        "role": "user",
        "content": message.content
    })
    
    # Keep only last 20 messages to avoid token limits
    if len(conversations[user_id]) > 20:
        conversations[user_id] = conversations[user_id][-20:]
    
    async with message.channel.typing():
        try:
            # Call Claude Messages API directly
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=conversations[user_id]
            )
            
            # Extract text response
            reply = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    reply += block.text
            
            # Add assistant response to history
            conversations[user_id].append({
                "role": "assistant",
                "content": reply
            })
            
            # Send response back to Discord
            if len(reply) > 2000:
                chunks = [reply[i:i+2000] for i in range(0, len(reply), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(reply or "I processed your request!")
            
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send(f"Sorry, I encountered an error: {str(e)[:200]}")

# Start health check server
Thread(target=run_health_server, daemon=True).start()

# Run the Discord bot
client.run(os.environ.get("DISCORD_BOT_TOKEN"))
