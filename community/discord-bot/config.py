"""Configuration and input validation for the Lightning Discord bot."""
from dataclasses import dataclass
import os
import re

_CHANNEL = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")

def parse_id(value: str, name: str) -> int:
    if not value.isdecimal() or int(value) <= 0:
        raise ValueError(f"{name} must be a positive Discord numeric ID")
    return int(value)

def validate_channel_name(name: str) -> str:
    if not _CHANNEL.fullmatch(name):
        raise ValueError("Channel name: 2-80 characters, lowercase letters, numbers or hyphens")
    return name

def validate_public_text(content: str) -> str:
    if not content.strip() or len(content) > 1900:
        raise ValueError("Message must contain 1-1900 characters")
    return content.strip()

@dataclass(frozen=True)
class Settings:
    token: str
    guild_id: int
    operator_ids: frozenset[int]
    feedback_channel_id: int | None

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        token = env.get("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN is required; keep it outside Git")
        guild_id = parse_id(env.get("DISCORD_GUILD_ID", ""), "DISCORD_GUILD_ID")
        owners = [x.strip() for x in env.get("DISCORD_OPERATOR_IDS", "").split(",") if x.strip()]
        if not owners:
            raise ValueError("DISCORD_OPERATOR_IDS must name at least one trusted user ID")
        operator_ids = frozenset(parse_id(owner, "DISCORD_OPERATOR_IDS") for owner in owners)
        raw = env.get("DISCORD_FEEDBACK_CHANNEL_ID", "").strip()
        feedback_id = parse_id(raw, "DISCORD_FEEDBACK_CHANNEL_ID") if raw else None
        return cls(token, guild_id, operator_ids, feedback_id)

    def is_operator(self, user_id: int, guild_id: int | None) -> bool:
        return guild_id == self.guild_id and user_id in self.operator_ids
