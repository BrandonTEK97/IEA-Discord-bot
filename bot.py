import os
import json
import discord
from anthropic import Anthropic
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, HtmlContent
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Initialize Discord client
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=os.environ.get("CLAUDE_API_KEY"))

# Initialize SendGrid
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDER_EMAIL = "aidan@igiehoneliteacademy.com"

# Define the email sending tool for Claude
EMAIL_TOOL = {
    "name": "send_email",
    "description": "Send an email using SendGrid. Use this tool whenever the user asks you to send, deliver, or email someone. Always confirm the details with the user before sending unless they've already provided all the info.",
    "input_schema": {
        "type": "object",
        "properties": {
            "to_email": {
                "type": "string",
                "description": "The recipient's email address"
            },
            "subject": {
                "type": "string",
                "description": "The email subject line"
            },
            "body": {
                "type": "string",
                "description": "The email body content in plain text"
            }
        },
        "required": ["to_email", "subject", "body"]
    }
}

def send_email(to_email, subject, body):
    """Send an email via SendGrid"""
    html_body = body.replace('\n', '<br>') + """
    <br><br>
    <p>Best regards,<br>
    <strong>IGE Academy Administrative Team</strong><br>
    Igiehon Elite Basketball Academy</p>
    <img src="https://i.imgur.com/ot785eY.jpeg" alt="IGE Academy" width="200">
    """
    
    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=HtmlContent(html_body)
    )
    
    # BCC for audit trail
    message.add_bcc("aidan@igiehoneliteacademy.com")
    
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        return f"Email sent successfully to {to_email}! (Status: {response.status_code})"
    except Exception as e:
        return f"Failed to send email: {str(e)}"

# Agent system prompt
SYSTEM_PROMPT = """You are the IGE Academy Administrative Assistant, an AI agent for Igiehon Elite Basketball Academy.

Your role:
- Help manage administrative tasks for the basketball academy
- Draft and send professional emails on behalf of the academy
- Help organize schedules, events, and communications
- Answer questions about academy operations
- Assist with parent/player communications

You have a send_email tool available. When the user asks you to send an email:
1. If they provide all details (to, subject, body) - use the tool immediately
2. If details are missing - ask for the missing information first
3. Always format the email body professionally

When drafting email content:
- Use a professional but friendly tone
- Keep it concise and clear
- The email signature is added automatically - do NOT include one in your body text

You are communicating via Discord DM with academy staff. Keep responses concise."""

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
    print(f'SendGrid: {"Connected" if SENDGRID_API_KEY else "Not configured"}')

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
    
    # Keep only last 20 messages
    if len(conversations[user_id]) > 20:
        conversations[user_id] = conversations[user_id][-20:]
    
    async with message.channel.typing():
        try:
            # Call Claude with the email tool
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=conversations[user_id],
                tools=[EMAIL_TOOL]
            )
            
            # Process the response - handle tool calls
            reply = ""
            tool_used = False
            
            for block in response.content:
                if hasattr(block, 'text'):
                    reply += block.text
                elif block.type == "tool_use" and block.name == "send_email":
                    tool_used = True
                    tool_input = block.input
                    
                    # Actually send the email
                    result = send_email(
                        to_email=tool_input["to_email"],
                        subject=tool_input["subject"],
                        body=tool_input["body"]
                    )
                    
                    # Send tool result back to Claude for a nice response
                    conversations[user_id].append({
                        "role": "assistant",
                        "content": response.content
                    })
                    conversations[user_id].append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        }]
                    })
                    
                    # Get Claude's final response after tool use
                    final_response = anthropic_client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=1024,
                        system=SYSTEM_PROMPT,
                        messages=conversations[user_id],
                        tools=[EMAIL_TOOL]
                    )
                    
                    reply = ""
                    for final_block in final_response.content:
                        if hasattr(final_block, 'text'):
                            reply += final_block.text
            
            # Add assistant response to history
            if not tool_used:
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
