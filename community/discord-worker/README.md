# Lightning Bot — Cloudflare Workers Free

This is the recommended **$0/month** deployment for Lightning's Discord command bot. It uses Discord's HTTP interactions (not a WebSocket Gateway), so no always-on VM or Python process is needed. It will often appear **offline** in Discord's member list; slash commands still work. The Python Gateway alternative remains in `../discord-bot/`.

## Security

- Verifies all interaction requests using Discord's Ed25519 public key with a 5-minute timestamp window.
- Limits interaction requests to the specified Discord server and application.
- Limits `post`, `channel`, `forum`, and `thread` to `OPERATOR_IDS`.
- Does not permit mass mentions; no financial records or full chat-message access.
- Keep `DISCORD_TOKEN` secret in the **Cloudflare Worker runtime secrets**, never in Git, issues, or chat.
- `feedback` posts to a designated private channel (configure its Discord permissions), with an ephemeral confirmation. Unlike the Python prototype it does not implement per-user cooldowns.
- Forum creation requires a Community-enabled server where applicable.

## Setup (Cloudflare dashboard)

1. Create a **Cloudflare** account and select the Workers **Free** plan, not a paid plan.
2. Navigate to **Workers & Pages → Create application → Import a Git repository**. Select `LightningEg/Lightning`, branch containing this feature, and **Root directory: `community/discord-worker`**.
3. Use Worker name `lightning-discord-bot`, matching `wrangler.toml`. Deploy. No public domain purchase is required.
4. In the new Worker → **Settings → Variables and Secrets**, add the following runtime values (use Secret for the bot token):

| Name | Where to find it |
| --- | --- |
| `APP_ID` | Discord Developer Portal → General Information → Application ID |
| `GUILD_ID` | Discord Server ID (Developer Mode) |
| `OPERATOR_IDS` | Comma-separated allowed Discord user IDs |
| `PUBLIC_KEY` | Developer Portal → General Information → Public Key (not client secret) |
| `DISCORD_TOKEN` | Developer Portal → Bot → Token (**secret**) |
| `FEEDBACK_CHANNEL_ID` | Optional private channel's ID; omit to disable submissions |

5. Find the deployed URL, e.g. `https://lightning-discord-bot.YOUR-SUBDOMAIN.workers.dev`. In Discord Developer Portal → **General Information → Interactions Endpoint URL**, save `https://lightning-discord-bot.YOUR-SUBDOMAIN.workers.dev/interactions`. Discord verifies the signature and PING response.
6. Register `/lightning` **once** using `register.mjs` (Node.js 20+, shell environment). This script **overwrites commands only for this application in the configured server**:

```bash
cd community/discord-worker
export APP_ID=YOUR_DISCORD_APPLICATION_ID
export GUILD_ID=YOUR_SERVER_ID
read -rs DISCORD_TOKEN && export DISCORD_TOKEN # pasted locally; never send in chat
node register.mjs
unset DISCORD_TOKEN
```

In Windows PowerShell, set the three variables using `$env:APP_ID=...`, `$env:GUILD_ID=...`, and `$env:DISCORD_TOKEN=(Read-Host -AsSecureString ...)` **is not directly supported by Node** (secure strings must be deliberately converted in-process). Use a local secret-manager-based environment injector or perform one-time registration from a trusted terminal, and clear the session variable afterward. Never paste the token into a shell command history, repository or screenshots.

7. Run **`/lightning ping`** in the Lightning server; it should respond privately. Test other commands with only a test channel first.

## Commands

- `/lightning ping`: health confirmation.
- `/lightning post`: operator announcement in text channel.
- `/lightning channel` / `forum`: operator channel creation.
- `/lightning thread`: operator text-channel thread creation.
- `/lightning feedback`: member feedback to private channel.

Run `node --test` in this folder. Live Discord configuration and deployment are still required.

## ChatGPT control

Hosting alone does **not** allow ChatGPT to control the bot. A separately authenticated bridge with user-approved operations, rate limiting and audit records is a future step. Do not create a publicly exposed unauthenticated command endpoint.
