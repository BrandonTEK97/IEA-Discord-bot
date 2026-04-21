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

# Composio MCP configuration
COMPOSIO_MCP_URL = os.environ.get("COMPOSIO_MCP_URL", "https://backend.composio.dev/api/v1/mcp")
COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")

# Agent system prompt
SYSTEM_PROMPT = """You are the IGE Academy Administrative Assistant, an AI agent for Igiehon Elite (IGE) Basketball Academy.

Your role:
- Help manage administrative tasks for the basketball academy
- Draft and send professional emails on behalf of the academy
- Help organize schedules, events, and communications
- Answer questions about academy operations
- Assist with parent/player communications

You have access to tools via Composio MCP including:
- SendGrid: For sending professional emails
- Gmail: For reading and managing emails
- Google Calendar: For scheduling and events
- Google Drive: For document management
- Google Sheets: For data and records

When sending emails:
- Always use a professional but friendly tone
- Include "Igiehon Elite Basketball Academy" in formal communications
- Use the SendGrid tool to actually send emails when asked
- Always confirm with the user before sending

Email Signature to include in all outgoing emails:
Best regards,
IGE Academy Administrative Team
Igiehon Elite Basketball Academy

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
    print(f'Composio MCP: {"Connected" if COMPOSIO_API_KEY else "Not configured"}')

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
            # Build MCP server config if Composio is available
            mcp_config = []
            extra_headers = {}
            use_beta = False
            
            if COMPOSIO_API_KEY:
                mcp_config = [{
                    "type": "url",
                    "url": COMPOSIO_MCP_URL,
                    "name": "composio-mcp",
                    "headers": {"x-api-key": COMPOSIO_API_KEY},
                }]
                use_beta = True
            
            # Call Claude with MCP tools if available
            if use_beta and mcp_config:
                response = anthropic_client.beta.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=conversations[user_id],
                    mcp_servers=mcp_config,
                    betas=["mcp-client-2025-04-04"]
                )
            else:
                response = anthropic_client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
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
            if not reply:
                reply = "I processed your request successfully!"
            
            if len(reply) > 2000:
                chunks = [reply[i:i+2000] for i in range(0, len(reply), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(reply)
            
        except Exception as e:
            print(f"Error: {e}")
            error_msg = str(e)[:200]
            await message.channel.send(f"Sorry, I encountered an error: {error_msg}")

# Start health check server
Thread(target=run_health_server, daemon=True).start()

# Run the Discord bot
client.run(os.environ.get("DISCORD_BOT_TOKEN"))
