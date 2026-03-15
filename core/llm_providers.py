from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    base_url: str
    default_model: str
    model_options: list[str]
    supports_custom_base_url: bool = False


@dataclass(frozen=True)
class ResolvedLLMConfig:
    provider: str
    label: str
    base_url: str
    model: str


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        key="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com",
        default_model="deepseek-chat",
        model_options=["deepseek-chat", "deepseek-reasoner"],
    ),
    "openai": ProviderSpec(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1-mini",
        model_options=["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"],
    ),
    "kimi": ProviderSpec(
        key="kimi",
        label="Kimi",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        model_options=[
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "kimi-latest",
            "kimi-thinking-preview",
        ],
    ),
    "anthropic": ProviderSpec(
        key="anthropic",
        label="Anthropic",
        base_url="https://api.anthropic.com/v1/",
        default_model="claude-sonnet-4-20250514",
        model_options=[
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest",
            "claude-3-5-haiku-latest",
        ],
    ),
    "glm": ProviderSpec(
        key="glm",
        label="GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-plus",
        model_options=["glm-4-plus", "glm-4-air", "glm-4-flash"],
    ),
    "minimax": ProviderSpec(
        key="minimax",
        label="MiniMax",
        base_url="https://api.minimaxi.com/v1",
        default_model="MiniMax-M2.5",
        model_options=[
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
            "MiniMax-M2",
        ],
    ),
    "openai_compatible": ProviderSpec(
        key="openai_compatible",
        label="OpenAI-Compatible",
        base_url="",
        default_model="",
        model_options=[],
        supports_custom_base_url=True,
    ),
}


def resolve_llm_config(
    provider: str = "deepseek",
    model: str | None = None,
    base_url: str | None = None,
) -> ResolvedLLMConfig:
    provider_key = (provider or "deepseek").strip().lower()
    spec = PROVIDER_SPECS.get(provider_key)
    if spec is None:
        valid = ", ".join(sorted(PROVIDER_SPECS))
        raise ValueError(f"Unsupported provider: {provider}. Available providers: {valid}")

    resolved_base_url = (base_url or spec.base_url).strip()
    resolved_model = (model or spec.default_model).strip()

    if spec.supports_custom_base_url and not resolved_base_url:
        raise ValueError(f"Provider '{provider_key}' requires a base URL.")
    if not resolved_model:
        raise ValueError(f"Provider '{provider_key}' requires a model.")

    return ResolvedLLMConfig(
        provider=spec.key,
        label=spec.label,
        base_url=resolved_base_url,
        model=resolved_model,
    )


def get_provider_catalog() -> list[dict[str, object]]:
    return [
        {
            **asdict(spec),
            "base_url_required": spec.supports_custom_base_url and not bool(spec.base_url),
        }
        for spec in PROVIDER_SPECS.values()
    ]
