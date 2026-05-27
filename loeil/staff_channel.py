from datetime import datetime
from typing import Any

import discord

from loeil import config, prompts


_EMBED_FIELD_MAX = 1024
_TRUNCATION_SUFFIX = "…"

_NIVEAU_COLORS: dict[str, int] = {
    "PROFIL FORT": 0x22C55E,
    "À SURVEILLER": 0xF59E0B,
    "REJETÉ": 0xEF4444,
}
_DEFAULT_COLOR = 0x1F2937


def _truncate(text: str, limit: int = _EMBED_FIELD_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


def build_embed(
    candidate: discord.abc.User,
    started_at: datetime,
    answers: dict[str, Any],
) -> discord.Embed:
    niveau = str(answers.get("niveau") or "")
    score = answers.get("score")
    tags: list[str] = list(answers.get("tags") or [])
    synthese = str(answers.get("synthese") or "—")

    color = _NIVEAU_COLORS.get(niveau, _DEFAULT_COLOR)
    title = f"Nouvelle candidature — {niveau}" if niveau else "Nouvelle candidature"

    description_parts = [
        f"**Candidat :** {candidate.mention} (`{candidate}`)",
        f"**Date :** {started_at.strftime('%Y-%m-%d %H:%M')}",
    ]
    if score is not None:
        tags_str = " ".join(f"[{t}]" for t in tags) if tags else ""
        score_line = f"Score : {score}/10"
        if tags_str:
            score_line += f"  {tags_str}"
        description_parts.append(score_line)

    embed = discord.Embed(
        title=title,
        description="\n".join(description_parts),
        color=color,
    )

    embed.add_field(
        name="Verdict de L'Œil",
        value=_truncate(synthese),
        inline=False,
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
    answers: dict[str, Any],
) -> None:
    channel = bot.get_channel(config.STAFF_CHANNEL_ID)
    if channel is None:
        channel = await bot.fetch_channel(config.STAFF_CHANNEL_ID)
    embed = build_embed(candidate, started_at, answers)
    await channel.send(embed=embed)
