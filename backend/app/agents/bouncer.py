"""
Bouncer — the hard-line safety filter. First agent in the critical path.
Runs before IntentRouter, RulesLawyer, and DM Agent.

Two-layer approach:
  Layer 1: Instant Python keyword/pattern check (zero latency, zero tokens).
  Layer 2: Ollama semantic check for edge cases that keywords miss.

Returns:
  BouncerVerdict with allowed=True/False + reason string.

Design rule: When in doubt, ALLOW. This is a grimdark RPG — violence,
moral ambiguity, and dark themes are expected and permitted.
We only block a narrow set of hard limits defined in config.
"""

import asyncio
import json
import re

import ollama

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.schemas.contracts import SocketMessage


# ── Hard-limit patterns (Layer 1 — instant, no LLM) ─────────────────────────
# These are the ONLY categories that are unconditionally blocked.
# Keep this list SHORT and specific. Do not add vague moral judgements.

_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b(sexual|explicit)\s+content\s+(involving|with)\s+(minor|child|kid|underage)', re.I),
    re.compile(r'\b(csam|child\s+porn|loli)\b', re.I),
    re.compile(r'\breal\s+(bomb|explosive)\s+(instruction|recipe|how.?to)', re.I),
    re.compile(r'\bsynthesize\s+(nerve\s+agent|sarin|vx\s+gas|anthrax)', re.I),
]

# Themes that are explicitly ALLOWED despite sounding alarming.
# The Bouncer must not block these — they are core RPG content.
_ALLOWED_CONTEXT_HINTS = (
    "violence", "murder", "kill", "attack", "torture", "dark", "evil",
    "blood", "death", "fight", "steal", "poison", "assassin", "demon",
    "undead", "necromancer", "corruption", "war", "execution",
)

_LAYER2_SYSTEM = """
You are a content safety classifier for a grimdark solo D&D 5e RPG engine.
Your job is NARROW: only flag content that is unambiguously in these categories:
  1. Sexual content involving minors
  2. Real-world instructions for weapons of mass destruction
  3. Content designed to facilitate real-world violence against a specific named person

IMPORTANT rules:
- Fantasy violence, murder, torture, moral evil, dark themes = ALLOWED (this is grimdark D&D)
- Asking to play evil characters = ALLOWED
- Profanity, crude language = ALLOWED
- Anything that is clearly fictional RPG content = ALLOWED
- Only block if you are CERTAIN it falls into categories 1-3 above

Return ONLY a JSON object:
{"allowed": true, "reason": ""}
or
{"allowed": false, "reason": "one sentence explanation"}

No markdown. No explanation outside the JSON.
"""


class BouncerVerdict:
    """Result object returned by the Bouncer."""
    __slots__ = ("allowed", "reason", "layer")

    def __init__(self, allowed: bool, reason: str = "", layer: int = 0) -> None:
        self.allowed = allowed
        self.reason  = reason
        self.layer   = layer  # 1 = pattern match, 2 = LLM semantic, 0 = passed


class Bouncer(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="Bouncer")

    # ── Public entrypoint ─────────────────────────────────────────────────────

    async def process(
        self, context: dict, message: SocketMessage
    ) -> BouncerVerdict:
        """
        Run both layers. Returns a BouncerVerdict.
        Layer 1 is synchronous and runs first — if it blocks, Layer 2 is skipped.
        """
        text = message.content.strip()

        # Layer 1 — instant pattern check
        verdict = self._layer1_pattern_check(text)
        if not verdict.allowed:
            return verdict

        # Layer 2 — semantic LLM check (only for ambiguous edge cases)
        # Skip if the message is clearly safe RPG content
        if self._is_obvious_rp(text):
            return BouncerVerdict(allowed=True, layer=0)

        return await self._layer2_semantic_check(text)

    # ── Layer 1 ───────────────────────────────────────────────────────────────

    def _layer1_pattern_check(self, text: str) -> BouncerVerdict:
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(text):
                return BouncerVerdict(
                    allowed=False,
                    reason="Content violates hard-limit safety rules.",
                    layer=1,
                )
        return BouncerVerdict(allowed=True, layer=1)

    def _is_obvious_rp(self, text: str) -> bool:
        """
        Expanded fast-path for 1b models — skip LLM for anything
        that looks like standard RPG input. Returns True = skip Layer 2.
        """
        lower = text.lower()

        # Any message under 120 chars that doesn't contain real-world
        # trigger words is almost certainly safe RPG content
        real_world_triggers = (
            "instruction", "recipe", "synthesize", "how to make",
            "teach me", "real world", "actual steps",
        )
        has_trigger = any(t in lower for t in real_world_triggers)

        if not has_trigger and len(text) <= 120:
            return True  # fast-path: skip Layer 2 entirely

        # Longer messages — check for RP verbs as secondary signal
        rp_verbs = (
            "i attack", "i search", "i open", "i pick", "i cast", "i run",
            "i hide", "i talk", "i ask", "i look", "i move", "i go",
            "i try", "i draw", "i sneak", "i climb", "i jump", "i grab",
            "i drink", "i eat", "i rest", "i wait", "i listen", "i examine",
            "i check", "i roll", "i use", "i equip", "i throw", "i dodge",
        )
        has_rp_verb = any(lower.startswith(w) or f" {w}" in lower for w in rp_verbs)
        return has_rp_verb and not has_trigger

    async def _layer2_semantic_check(self, text: str) -> BouncerVerdict:
        """
        Layer 2 only runs for genuinely ambiguous content.
        With the expanded fast-path above, this should almost never fire.
        Always fails OPEN on any error — never block gameplay.
        """
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _LAYER2_SYSTEM},
                    {"role": "user",   "content": f"Player input: {text}"},
                ],
                format="json",
                options={"temperature": 0.0},
            )
            result = json.loads(response["message"]["content"])
            allowed = bool(result.get("allowed", True))  # default True if key missing
            reason  = str(result.get("reason", ""))
            # Extra safety net: if the model blocked something containing
            # only known RPG words, override it and allow
            if not allowed:
                lower = text.lower()
                if any(w in lower for w in _ALLOWED_CONTEXT_HINTS):
                    print(f"[Bouncer] Layer 2 false positive overridden for: {text[:60]}")
                    return BouncerVerdict(allowed=True, layer=2)
            return BouncerVerdict(allowed=allowed, reason=reason, layer=2)

        except Exception as exc:
            print(f"[Bouncer] Layer 2 error, failing open: {exc}")
            return BouncerVerdict(allowed=True, reason="", layer=2)