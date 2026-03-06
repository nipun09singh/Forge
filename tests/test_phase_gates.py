"""Tests for forge.runtime.phase_gates — hard phase enforcement."""

import pytest
from forge.runtime.phase_gates import Phase, PhaseGateEnforcer, PhaseStatus, PHASE_REQUIREMENTS


class TestPhaseEnum:
    def test_phase_values(self):
        assert Phase.RESEARCH == "research"
        assert Phase.BUILD == "build"
        assert Phase.TEST == "test"
        assert Phase.VERIFY == "verify"
        assert Phase.COMPLETE == "complete"


class TestPhaseGateInit:
    def test_starts_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        assert e.current_phase == Phase.RESEARCH

    def test_research_entered(self):
        e = PhaseGateEnforcer("/tmp/test")
        assert e._phases[Phase.RESEARCH].entered is True

    def test_other_phases_not_entered(self):
        e = PhaseGateEnforcer("/tmp/test")
        assert e._phases[Phase.BUILD].entered is False
        assert e._phases[Phase.TEST].entered is False
        assert e._phases[Phase.VERIFY].entered is False


class TestResearchPhaseGate:
    """RESEARCH phase: must use browse_web or web_search AND spend ≥2 iterations."""

    def test_cannot_skip_research(self):
        """Without research tools, stays in RESEARCH forever."""
        e = PhaseGateEnforcer("/tmp/test")
        for _ in range(20):
            e.tick()
        assert e.current_phase == Phase.RESEARCH, "Must not skip research without research tools"

    def test_research_requires_tool(self):
        """Must use browse_web or web_search to complete research."""
        e = PhaseGateEnforcer("/tmp/test")
        e.tick()
        e.tick()
        e.tick()
        assert e.current_phase == Phase.RESEARCH

    def test_research_advances_with_browse_web(self):
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("browse_web")
        e.tick()
        e.tick()  # min 2 iterations
        assert e.current_phase == Phase.BUILD

    def test_research_advances_with_web_search(self):
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("web_search")
        e.tick()
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_no_bypass_at_5_iterations(self):
        """The old _total_iterations > 5 bypass must not exist."""
        e = PhaseGateEnforcer("/tmp/test")
        for _ in range(10):
            e.tick()
        assert e.current_phase == Phase.RESEARCH, "Must not bypass research after N iterations"

    def test_no_bypass_at_100_iterations(self):
        """Even at 100 iterations, research is not bypassed without tools."""
        e = PhaseGateEnforcer("/tmp/test")
        for _ in range(100):
            e.tick()
        assert e.current_phase == Phase.RESEARCH


class TestBuildPhaseGate:
    """BUILD phase: must create ≥2 Python files."""

    def _enter_build(self, e: PhaseGateEnforcer):
        e.record_tool_use("browse_web")
        e.tick()
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_build_needs_python_files(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_build_advances_with_2_py_files(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.record_file_created("main.py")
        e.record_file_created("utils.py")
        e.tick()
        assert e.current_phase == Phase.TEST

    def test_build_not_enough_with_1_file(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.record_file_created("main.py")
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_non_python_files_dont_count(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.record_file_created("README.md")
        e.record_file_created("config.yaml")
        e.tick()
        assert e.current_phase == Phase.BUILD


class TestTestPhaseGate:
    """TEST phase: tests must be RUN and must PASS."""

    def _enter_test(self, e: PhaseGateEnforcer):
        e.record_tool_use("browse_web")
        e.tick()
        e.tick()
        e.record_file_created("main.py")
        e.record_file_created("test_main.py")
        e.tick()
        assert e.current_phase == Phase.TEST

    def test_test_phase_needs_tests_run(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_test(e)
        e.tick()
        assert e.current_phase == Phase.TEST

    def test_test_run_but_failed_stays(self):
        """Running tests that fail must NOT advance."""
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_test(e)
        e.record_command_output("pytest tests/", "FAILED 2 tests")
        e.tick()
        assert e.current_phase == Phase.TEST, "Failed tests must not advance to VERIFY"
        assert e._phases[Phase.TEST].tests_run is True
        assert e._phases[Phase.TEST].test_passed is False

    def test_test_passed_advances(self):
        """Tests that pass advance to VERIFY."""
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_test(e)
        e.record_command_output("pytest tests/", "5 passed in 1.2s")
        e.tick()
        assert e.current_phase == Phase.VERIFY

    def test_test_detects_pytest_output(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_test(e)
        e.record_command_output("python -m pytest", "10 passed, 0 warnings")
        assert e._phases[Phase.TEST].tests_run is True
        assert e._phases[Phase.TEST].test_passed is True


class TestVerifyPhaseGate:
    """VERIFY phase: must have README and requirements.txt."""

    def _enter_verify(self, e: PhaseGateEnforcer):
        e.record_tool_use("browse_web")
        e.tick()
        e.tick()
        e.record_file_created("main.py")
        e.record_file_created("test_main.py")
        e.tick()
        e.record_command_output("pytest", "2 passed")
        e.tick()
        assert e.current_phase == Phase.VERIFY

    def test_verify_blocks_without_readme(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_file_created("requirements.txt")
        can, blockers = e.can_complete()
        assert can is False
        assert any("README" in b for b in blockers)

    def test_verify_blocks_without_requirements(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_file_created("README.md")
        can, blockers = e.can_complete()
        assert can is False
        assert any("requirements" in b for b in blockers)

    def test_verify_passes_with_both(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        can, blockers = e.can_complete()
        assert can is True
        assert blockers == []


class TestCanComplete:
    """Tests for the final can_complete() gate."""

    def test_cannot_complete_from_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        can, blockers = e.can_complete()
        assert can is False
        assert len(blockers) > 0

    def test_cannot_complete_without_tests_passing(self):
        """Even with all files, must have passing tests."""
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("browse_web")
        e.tick()
        e.tick()
        e.record_file_created("main.py")
        e.record_file_created("app.py")
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        # Tests run but failed
        e.record_command_output("pytest", "1 FAILED")
        can, blockers = e.can_complete()
        assert can is False
        assert any("pass" in b.lower() for b in blockers)

    def test_full_lifecycle_can_complete(self):
        """Full happy path: research -> build -> test (pass) -> verify -> DONE."""
        e = PhaseGateEnforcer("/tmp/test")
        # Research
        e.record_tool_use("web_search")
        e.tick()
        e.tick()
        assert e.current_phase == Phase.BUILD
        # Build
        e.record_file_created("main.py")
        e.record_file_created("utils.py")
        e.tick()
        assert e.current_phase == Phase.TEST
        # Test
        e.record_command_output("pytest tests/", "3 passed")
        e.tick()
        assert e.current_phase == Phase.VERIFY
        # Verify
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        can, blockers = e.can_complete()
        assert can is True
        assert blockers == []

    def test_blocker_feedback_is_informative(self):
        e = PhaseGateEnforcer("/tmp/test")
        feedback = e.get_blocker_feedback()
        assert "RESEARCH" in feedback
        assert "cannot complete" in feedback.lower()


class TestPhaseInstruction:
    """Tests for get_phase_instruction."""

    def test_research_instruction(self):
        e = PhaseGateEnforcer("/tmp/test")
        instr = e.get_phase_instruction()
        assert "RESEARCH" in instr
        assert "browse_web" in instr or "web_search" in instr

    def test_build_instruction(self):
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("browse_web")
        e.tick()
        e.tick()
        instr = e.get_phase_instruction()
        assert "BUILD" in instr

    def test_test_instruction(self):
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("browse_web")
        e.tick()
        e.tick()
        e.record_file_created("a.py")
        e.record_file_created("b.py")
        e.tick()
        instr = e.get_phase_instruction()
        assert "TEST" in instr or "test" in instr


class TestSummary:
    def test_summary_structure(self):
        e = PhaseGateEnforcer("/tmp/test")
        s = e.get_summary()
        assert s["current_phase"] == "research"
        assert "phases" in s
        assert "research" in s["phases"]
        assert "total_iterations" in s
