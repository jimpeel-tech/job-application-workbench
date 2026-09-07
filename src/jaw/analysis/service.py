"""Provider-neutral analysis orchestration service."""

from __future__ import annotations

from ..config import AppConfig
from .context import build_analysis_request
from .contracts import AnalysisProvider
from .normalization import normalize_result
from .providers.deterministic import DeterministicAnalysisProvider
from .providers.ollama import OllamaAnalysisProvider
from .providers.openai import OpenAIAnalysisProvider


class JobAnalyzer:
    """Coordinate context construction, provider selection, and normalization.

    Public methods intentionally preserve the existing JAW interface used by
    the desktop application: ``configure()``, ``test_connection()``,
    ``analyze()``, ``api_available``, and ``uses_generative_ai``.
    """

    def __init__(
        self,
        config: AppConfig,
        model: str | None = None,
        mode: str | None = None,
        provider: str | None = None,
    ) -> None:
        self.config = config
        self.model = model or config.analysis_model
        self.mode = mode or config.analysis_mode
        self.provider = provider or config.analysis_provider
        self._custom_providers: dict[str, AnalysisProvider] = {}
        self._refresh_builtin_providers()

    def _refresh_builtin_providers(self) -> None:
        self._local_provider = DeterministicAnalysisProvider(self.config)
        self._openai_provider = OpenAIAnalysisProvider(self.model)
        self._ollama_provider = OllamaAnalysisProvider(self.model)

    def register_provider(
        self,
        name: str,
        provider: AnalysisProvider,
    ) -> None:
        """Register a future local-LLM or other analysis provider."""
        normalized = str(name).strip().lower()
        if not normalized:
            raise ValueError("Provider name is required")
        self._custom_providers[normalized] = provider

    @property
    def uses_generative_ai(self) -> bool:
        return self.mode == "generative"

    @property
    def api_available(self) -> bool:
        try:
            return self._selected_provider().available
        except RuntimeError:
            return False

    def configure(self, config: AppConfig) -> None:
        self.config = config
        self.mode = config.analysis_mode
        self.provider = config.analysis_provider
        self.model = config.analysis_model
        self._refresh_builtin_providers()

    def _selected_provider(self) -> AnalysisProvider:
        if self.mode == "local":
            return self._local_provider

        provider_name = str(self.provider).strip().lower()
        if provider_name == "openai":
            return self._openai_provider
        if provider_name == "ollama":
            return self._ollama_provider

        custom = self._custom_providers.get(provider_name)
        if custom is not None:
            return custom

        raise RuntimeError(f"Unsupported analysis provider: {self.provider}")

    def test_connection(self) -> str:
        return self._selected_provider().test_connection()

    def analyze(
        self,
        description: str,
    ) -> tuple[dict[str, object], str]:
        request = build_analysis_request(self.config, description)
        result, model = self._selected_provider().analyze(request)
        return normalize_result(result), model
