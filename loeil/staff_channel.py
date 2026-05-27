from datetime import datetime

import discord

from loeil import config, prompts


_EMBED_FIELD_MAX = 1024
_TRUNCATION_SUFFIX = "…"


def _truncate(text: str, limit: int = _EMBED_FIELD_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


def build_embed(
    candidate: discord.abc.User,
    started_at: datetime,
    answers: dict[str, str],
) -> discord.Embed:
    embed = discord.Embed(
        title="Nouvelle candidature",
        description=(
            f"**Candidat :** {candidate.mention} (`{candidate}`)\n"
            f"**Date :** {started_at.strftime('%Y-%m-%d %H:%M')}"
        ),
        color=0x1F2937,
    )
    for index, question in enumerate(prompts.QUESTIONS, start=1):
        answer = answers.get(f"answer_{index}", "—") or "—"
        embed.add_field(
            name=f"Q{index}. {_truncate(question, 256)}",
            value=_truncate(answer),
            inline=False,
        )
    return embed


async def post_application(
    bot: discord.Client,
    candidate: discord.abc.User,
    started_at: datetime,
    answers: dict[str, str],
) -> None:
    channel = bot.get_channel(config.STAFF_CHANNEL_ID)
    if channel is None:
        channel = await bot.fetch_channel(config.STAFF_CHANNEL_ID)
    embed = build_embed(candidate, started_at, answers)
    await channel.send(embed=embed)
