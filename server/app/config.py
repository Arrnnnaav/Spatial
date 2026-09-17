"""Environment-driven settings. Everything optional: with nothing configured the server still
answers deterministically from the text under the mark."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # .env is a convenience, not a requirement
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None and value.strip().lower() in {"none", "off"}:
        return None  # explicit opt-out (e.g. OLLAMA_VISION_MODEL=none for text-only + OCR)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str | None
    model: str
    vision_model: str | None
    kind: str  # "openai" (chat/completions), "ollama" (native /api/chat), "anthropic" (messages), "bedrock" (Converse)

    @property
    def configured(self) -> bool:
        if self.kind == "bedrock":  # base_url holds the region; credentials come from the AWS chain (role/env/profile)
            return bool(self.base_url) and self.api_key == "1"
        return bool(self.base_url) and (self.kind == "ollama" or bool(self.api_key))


@dataclass
class Settings:
    host: str = _env("SPATIAL_HOST", "127.0.0.1")
    port: int = int(_env("SPATIAL_PORT", "8787"))
    api_token: str | None = _env("SPATIAL_API_TOKEN")
    db_path: str = _env(
        "SPATIAL_DB", str(Path(__file__).resolve().parents[1] / "spatial.db")
    )
    timeout_seconds: float = float(_env("SPATIAL_TIMEOUT_SECONDS", "30"))
    # Comma-separated order in which providers are tried; the first configured one that answers wins.
    provider_order: tuple[str, ...] = tuple(
        part.strip()
        for part in _env(
            "SPATIAL_PROVIDERS", "nvidia,ollama,openrouter,openai,anthropic,bedrock"
        ).split(",")
        if part.strip()
    )
    ocr_enabled: bool = _env("SPATIAL_OCR", "1") not in {"0", "false", "no"}
    stt_model: str = _env("SPATIAL_STT_MODEL", "base")
    stt_device: str = _env("SPATIAL_STT_DEVICE", "cpu")
    tts_voice: str = _env("SPATIAL_TTS_VOICE", "alba")
    tts_enabled: bool = _env("SPATIAL_TTS", "1") not in {"0", "false", "no"}
    # Free the speech models after this many idle seconds so Ollama has RAM again (0 = keep loaded).
    audio_idle_unload_seconds: int = int(_env("SPATIAL_AUDIO_IDLE_UNLOAD_SECONDS", "300"))
    # Some networks have a broken IPv6 route to Hugging Face; this makes model downloads use IPv4 only.
    force_ipv4: bool = _env("SPATIAL_FORCE_IPV4", "0") in {"1", "true", "yes"}
    providers: dict[str, ProviderConfig] = field(
        default_factory=lambda: {
            "ollama": ProviderConfig(
                "ollama",
                _env("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                None,
                _env("OLLAMA_MODEL", "qwen3:4b-instruct"),
                _env("OLLAMA_VISION_MODEL", "qwen2.5vl:3b"),
                "ollama",
            ),
            "openrouter": ProviderConfig(
                "openrouter",
                _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                _env("OPENROUTER_API_KEY"),
                _env("OPENROUTER_MODEL", "qwen/qwen3-4b:free"),
                _env("OPENROUTER_VISION_MODEL", "qwen/qwen2.5-vl-72b-instruct:free"),
                "openai",
            ),
            "nvidia": ProviderConfig(
                "nvidia",
                _env("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                _env("NVIDIA_API_KEY"),
                _env("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
                _env("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct"),
                "openai",
            ),
            "openai": ProviderConfig(
                "openai",
                _env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                _env("OPENAI_API_KEY"),
                _env("OPENAI_MODEL", "gpt-4o-mini"),
                _env("OPENAI_VISION_MODEL", "gpt-4o-mini"),
                "openai",
            ),
            "bedrock": ProviderConfig(
                "bedrock",
                _env("AWS_REGION", _env("AWS_DEFAULT_REGION", "")),
                "1" if _env("BEDROCK_ENABLED", "0") in {"1", "true", "yes"} else None,
                _env("BEDROCK_MODEL", "amazon.nova-lite-v1:0"),
                _env("BEDROCK_VISION_MODEL", "amazon.nova-lite-v1:0"),
                "bedrock",
            ),
            "anthropic": ProviderConfig(
                "anthropic",
                "https://api.anthropic.com/v1",
                _env("ANTHROPIC_API_KEY"),
                _env("ANTHROPIC_MODEL", "claude-sonnet-5"),
                _env("ANTHROPIC_VISION_MODEL", "claude-sonnet-5"),
                "anthropic",
            ),
        }
    )


settings = Settings()
