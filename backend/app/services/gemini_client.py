"""
GeminiClient — the ONLY module allowed to call google-generativeai.
Implements:
  - Round-robin API key rotation across unlimited keys
  - Per-key sliding-window RPM tracking (60-second window)
  - Async streaming via the official SDK
  - Prompt compression to enforce token budgets
  - Automatic backoff when all keys are saturated

NO other file should import google.generativeai directly.
"""

import asyncio
import time
from collections import deque
from typing import AsyncGenerator

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

CUSTOM_SAFETY_SETTINGS = [
    {
        "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        "threshold": HarmBlockThreshold.BLOCK_NONE,
    },
]

from app.core.config import settings


# ── Key Rotator ───────────────────────────────────────────────────────────────

class _KeyRotator:
    """
    Manages N API keys with a sliding 60-second RPM window per key.
    Hands out the next available key, blocking until one opens up.
    """

    def __init__(self, keys: list[str], rpm_limit: int) -> None:
        self._keys = keys
        self._rpm_limit = rpm_limit
        # Each key gets its own deque of call timestamps (last 60s)
        self._call_log: list[deque] = [deque() for _ in keys]
        self._cursor = 0  # round-robin pointer

    def _purge_expired(self, idx: int) -> None:
        """Remove timestamps older than 60 seconds from a key's log."""
        now = time.monotonic()
        log = self._call_log[idx]
        while log and now - log[0] > 60.0:
            log.popleft()

    def _find_available(self) -> int | None:
        """Return the index of the first key under RPM limit, or None."""
        for offset in range(len(self._keys)):
            idx = (self._cursor + offset) % len(self._keys)
            self._purge_expired(idx)
            if len(self._call_log[idx]) < self._rpm_limit:
                return idx
        return None

    async def acquire(self) -> tuple[str, int]:
        """
        Block until a key with remaining quota is available.
        Returns (api_key_string, key_index).
        Uses exponential backoff if all keys are saturated.
        """
        backoff = 1.0
        while True:
            idx = self._find_available()
            if idx is not None:
                self._call_log[idx].append(time.monotonic())
                self._cursor = (idx + 1) % len(self._keys)  # advance for fairness
                return self._keys[idx], idx

            # All keys saturated — wait for the soonest expiry
            all_logs = [log for log in self._call_log if log]
            if all_logs:
                soonest_expiry = min(log[0] for log in all_logs)
                wait = max(0.5, 60.0 - (time.monotonic() - soonest_expiry) + 0.5)
            else:
                wait = 5.0

            print(f"[GeminiClient] All keys at RPM limit. Waiting {wait:.1f}s...")
            await asyncio.sleep(min(wait, backoff))
            backoff = min(backoff * 1.5, 30.0)


# ── Main Client ───────────────────────────────────────────────────────────────

class GeminiClient:
    """
    Async Gemini client with key rotation, RPM tracking, and streaming.

    Usage (from dm_agent.py only):
        async for token in gemini_client.stream(system, user, history, turn_id):
            yield token
    """

    def __init__(self) -> None:
        keys = settings.get_gemini_keys()
        self._rotator = _KeyRotator(keys, rpm_limit=settings.GEMINI_RPM_LIMIT)
        self._model_name = settings.GEMINI_MODEL
        self._max_tokens = settings.GEMINI_MAX_OUTPUT_TOKENS
        self._temperature = settings.DM_TEMPERATURE

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[str],
        turn_id: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Stream narrative tokens from Gemini.

        Args:
            system_prompt: DM persona + world context (will be compressed).
            user_prompt:   Player action + injected rules (will be compressed).
            history:       Recent narrative turns (already windowed by caller).
            turn_id:       For log correlation.

        Yields:
            Individual text tokens as they arrive.
        """
        # Compress both prompts to stay within budget
        compressed_system = _compress(
            system_prompt,
            budget_tokens=settings.GEMINI_SYSTEM_PROMPT_TOKEN_BUDGET,
        )
        compressed_user = _compress(
            user_prompt,
            budget_tokens=settings.GEMINI_USER_PROMPT_TOKEN_BUDGET,
        )

        # Acquire a key that has remaining quota
        api_key, key_idx = await self._rotator.acquire()
        print(f"[GeminiClient] turn={turn_id} using key[{key_idx}] (last 4: ...{api_key[-4:]})")

        # Configure the SDK for this specific call
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=compressed_system,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=self._max_tokens,
                temperature=self._temperature,
            ),
        )

        # Build minimal chat history — only the windowed beats
        chat_history = [
            {"role": "user", "parts": [beat]}
            for beat in history
        ]

        try:
            chat = model.start_chat(history=chat_history)
            response = await chat.send_message_async(compressed_user, stream=True)
            async for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            print(f"[GeminiClient] Stream error on key[{key_idx}]: {exc}")
            raise


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compress(text: str, budget_tokens: int) -> str:
    """
    Trim a prompt to fit within a token budget.
    Approximation: 1 token ≈ 4 English characters.
    Trims from the middle to preserve the system persona (start)
    and the most recent instructions (end).
    """
    char_budget = budget_tokens * 4
    if len(text) <= char_budget:
        return text

    keep = char_budget // 2
    trimmed = (
        text[:keep]
        + "\n\n[...context trimmed for token budget...]\n\n"
        + text[-keep:]
    )
    print(
        f"[GeminiClient] Prompt compressed: {len(text)} → {len(trimmed)} chars"
    )
    return trimmed


# Singleton — import this, not the class
gemini_client = GeminiClient()