// One-time application command registration. Run locally with DISCORD_TOKEN in your shell, never in Git.
import { COMMAND } from './src/commands.mjs';
const app = process.env.APP_ID;
const guild = process.env.GUILD_ID;
const token = process.env.DISCORD_TOKEN;
if (!/^\d{16,22}$/.test(app || '') || !/^\d{16,22}$/.test(guild || '') || !token) {
  console.error('Set APP_ID, GUILD_ID and DISCORD_TOKEN in your shell environment.');
  process.exit(1);
}
const response = await fetch(`https://discord.com/api/v10/applications/${app}/guilds/${guild}/commands`, {
  method: 'PUT', headers: { Authorization: `Bot ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify([COMMAND])
});
if (!response.ok) {
  console.error(`Discord command registration failed (HTTP ${response.status}).`);
  process.exit(1);
}
console.log('Registered /lightning with 6 subcommands for the configured server.');
