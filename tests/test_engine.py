"""Tests for forge.core.engine — the meta-factory."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

from forge.core.engine import ForgeEngine
from forge.core.blueprint import AgencyBlueprint


class TestForgeEngineInit:
    """Tests for ForgeEngine initialization."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_defaults(self, mock_refine, mock_critic, mock_eval,
                           mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine()
        mock_llm.assert_called_once_with(model=None, api_key=None, base_url=None)
        assert engine._history == []

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_custom_model(self, mock_refine, mock_critic, mock_eval,
                               mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine(model="gpt-4o", api_key="sk-test", base_url="http://localhost")
        mock_llm.assert_called_once_with(model="gpt-4o", api_key="sk-test", base_url="http://localhost")

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_custom_output_dir(self, mock_refine, mock_critic, mock_eval,
                                    mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine(output_dir=Path("/custom/output"))
        mock_gen.assert_called_once_with(output_base=Path("/custom/output"))

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_creates_analyzer(self, mock_refine, mock_critic, mock_eval,
                                   mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine()
        mock_analyzer.assert_called_once_with(engine.llm)

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_init_creates_refinement_loop(self, mock_refine, mock_critic, mock_eval,
                                          mock_gen, mock_analyzer, mock_llm):
        engine = ForgeEngine()
        mock_refine.assert_called_once()
        call_kwargs = mock_refine.call_args[1]
        assert call_kwargs["max_iterations"] == 10


class TestCreateAgencySignature:
    """Tests for create_agency method existence and signature."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_create_agency_is_async(self, *mocks):
        engine = ForgeEngine()
        import asyncio
        assert asyncio.iscoroutinefunction(engine.create_agency)

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_create_agency_accepts_domain_description(self, *mocks):
        import inspect
        engine = ForgeEngine()
        sig = inspect.signature(engine.create_agency)
        assert "domain_description" in sig.parameters
        assert "overwrite" in sig.parameters

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    def test_list_generated_is_async(self, *mocks):
        engine = ForgeEngine()
        import asyncio
        assert asyncio.iscoroutinefunction(engine.list_generated)


class TestCreateAgencyErrorHandling:
    """Tests for create_agency error handling paths."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_create_agency_retries_on_analysis_failure(self, mock_refine, mock_critic,
                                                              mock_eval, mock_gen, mock_analyzer, mock_llm):
        """When first analyze() fails, engine retries with simpler prompt."""
        engine = ForgeEngine()

        # First call fails, second succeeds
        mock_blueprint = MagicMock(spec=AgencyBlueprint)
        mock_blueprint.name = "Test Agency"
        mock_blueprint.description = "desc"
        mock_blueprint.teams = []
        mock_blueprint.all_agents = []
        mock_blueprint.all_tools = []
        mock_blueprint.workflows = []
        mock_blueprint.api_endpoints = []
        engine.analyzer.analyze = AsyncMock(side_effect=[RuntimeError("API error"), mock_blueprint])

        engine.refinement_loop.refine = AsyncMock(return_value=(mock_blueprint, [{"combined_score": 0.9}]))
        engine.refinement_loop._history = [{"combined_score": 0.9}]
        engine.generator.generate = MagicMock(return_value=Path("/tmp/output"))

        with patch.object(engine, "_package_runtime"), \
             patch.object(engine, "_print_summary"), \
             patch("forge.core.engine.inject_archetypes", return_value=mock_blueprint), \
             patch("forge.generators.validator.AgencyValidator") as mock_validator_cls:
            mock_validator_cls.return_value.validate.return_value = MagicMock(
                passed=True, files_checked=5, errors=[], warnings=[]
            )
            bp, path = await engine.create_agency("test domain")

        assert engine.analyzer.analyze.call_count == 2
        assert bp == mock_blueprint

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_create_agency_raises_after_double_failure(self, mock_refine, mock_critic,
                                                              mock_eval, mock_gen, mock_analyzer, mock_llm):
        """When both analyze() calls fail, raises RuntimeError."""
        engine = ForgeEngine()
        engine.analyzer.analyze = AsyncMock(side_effect=RuntimeError("API error"))

        with pytest.raises(RuntimeError, match="Agency generation failed after retry"):
            await engine.create_agency("test domain")

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_create_agency_records_history(self, mock_refine, mock_critic,
                                                  mock_eval, mock_gen, mock_analyzer, mock_llm):
        """Successful creation is recorded in _history."""
        engine = ForgeEngine()

        mock_blueprint = MagicMock(spec=AgencyBlueprint)
        mock_blueprint.name = "History Test"
        mock_blueprint.description = "desc"
        mock_blueprint.teams = []
        mock_blueprint.all_agents = []
        mock_blueprint.all_tools = []
        mock_blueprint.workflows = []
        mock_blueprint.api_endpoints = []
        engine.analyzer.analyze = AsyncMock(return_value=mock_blueprint)
        engine.refinement_loop.refine = AsyncMock(return_value=(mock_blueprint, [{"combined_score": 0.95}]))
        engine.refinement_loop._history = [{"combined_score": 0.95}]
        engine.generator.generate = MagicMock(return_value=Path("/tmp/out"))

        with patch.object(engine, "_package_runtime"), \
             patch.object(engine, "_print_summary"), \
             patch("forge.core.engine.inject_archetypes", return_value=mock_blueprint), \
             patch("forge.generators.validator.AgencyValidator") as mock_validator_cls:
            mock_validator_cls.return_value.validate.return_value = MagicMock(
                passed=True, files_checked=3, errors=[], warnings=[]
            )
            await engine.create_agency("history domain")

        assert len(engine._history) == 1
        assert engine._history[0]["agency"] == "History Test"


class TestListGenerated:
    """Tests for listing previously generated agencies."""

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_list_generated_empty_dir(self, *mocks):
        import tempfile
        engine = ForgeEngine()
        with tempfile.TemporaryDirectory() as td:
            engine.generator.output_base = Path(td)
            result = await engine.list_generated()
            assert result == []

    @patch("forge.core.engine.LLMClient")
    @patch("forge.core.engine.DomainAnalyzer")
    @patch("forge.core.engine.AgencyGenerator")
    @patch("forge.core.engine.BlueprintEvaluator")
    @patch("forge.core.engine.BlueprintCritic")
    @patch("forge.core.engine.RefinementLoop")
    @pytest.mark.asyncio
    async def test_list_generated_nonexistent_dir(self, *mocks):
        engine = ForgeEngine()
        engine.generator.output_base = Path("/nonexistent/path/that/does/not/exist")
        result = await engine.list_generated()
        assert result == []
