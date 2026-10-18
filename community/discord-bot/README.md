# Lightning Discord Bot

Independent Discord community bot. It does **not** access the Lightning financial app or financial records and is **not yet controllable from ChatGPT**.

## Commands

- `/lightning ping` — private online status.
- `/lightning post` — publish a message in a specified text channel (operator only, mentions disabled).
- `/lightning channel` — create a text channel (operator only).
- `/lightning forum` — create a forum channel (operator only).
- `/lightning thread` — create a public thread and its opening post (operator only).
- `/lightning feedback` — modal to submit suggestions to a private feedback channel. One submission per user every five minutes.

Only specific human operator IDs in one configured server can run management commands.

## Set up Discord

1. Create **Lightning Bot** at https://discord.com/developers/applications.
2. Install it in the server with scopes `bot` and `applications.commands`; permissions: View Channels, Send Messages, Read Message History, Embed Links, Send Messages in Threads, Create Public Threads, Manage Channels, Manage Threads. **Do not grant Administrator.** Privileged Message Content Intent is not required.
3. Enable **Developer Mode** in Discord Settings > Advanced. Right-click the **server** > Copy Server ID; right-click **your user profile** > Copy User ID.
4. Under Developer Portal > Bot, reset/copy the bot token **into your hosting provider's secret environment variables**. Never paste it into a chat, issue, or Git. If exposed, regenerate immediately.
5. Optionally create a private team-only feedback channel and copy its channel ID. Ensure the bot can post there.

## Configure and run

Set these environment variables (see `.env.example`):

- `DISCORD_BOT_TOKEN` (secret)
- `DISCORD_GUILD_ID` (server ID)
- `DISCORD_OPERATOR_IDS` (comma-separated trusted Discord human user IDs)
- `DISCORD_FEEDBACK_CHANNEL_ID` (optional channel for private feedback)

Python 3.11+:

```bash
cd community/discord-bot
python -m pip install -r requirements.txt
python bot.py
```

Docker, from `community/discord-bot`:

```bash
docker build -t lightning-discord-bot .
docker run -d --restart unless-stopped --name lightning-discord-bot --env-file /secure/path/lightning-discord.env lightning-discord-bot
```

On a managed host, deploy `community/discord-bot` as a **long-running worker** or Docker service with restart-on-failure. The Discord Gateway bot requires outbound HTTPS/WebSocket but no public inbound port. Short-lived GitHub Actions jobs are not suitable for continuous hosting. After the bot connects, run `/lightning ping` in your server.

## Security and future ChatGPT control

No financial records or app credentials; no privileged message-content intent; no reading general Discord chat. No server token, confidential messages or remote command queue in the public Lightning GitHub repositories.

The next milestone is a **separately authenticated control bridge**. It must authenticate the caller, restrict actions to the allowed server/channels, provide audit logs and ask for approval before destructive actions. Simply installing this bot does **not** grant ChatGPT the ability to operate it.

Existing Discord GitHub-feed webhook in `docs/COLLABORATION.md` can continue separately.

Tests: `python -m unittest discover -s community/discord-bot/tests`. A live Discord test remains necessary after deployment.
