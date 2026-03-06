"""Tests for forge.runtime.phase_gates -- hard phase enforcement."""

import pytest
from forge.runtime.phase_gates import Phase, PhaseGateEnforcer, PhaseStatus, PHASE_REQUIREMENTS


class TestPhaseEnum:
    def test_phase_values(self):
        assert Phase.RESEARCH == "research"
        assert Phase.PLAN == "plan"
        assert Phase.BUILD == "build"
        assert Phase.VERIFY == "verify"
        assert Phase.SHIP == "ship"
        assert Phase.COMPLETE == "complete"

    def test_phase_order(self):
        """Phases must be RESEARCH -> PLAN -> BUILD -> VERIFY -> SHIP -> COMPLETE."""
        phases = list(Phase)
        assert phases == [Phase.RESEARCH, Phase.PLAN, Phase.BUILD, Phase.VERIFY, Phase.SHIP, Phase.COMPLETE]


class TestPhaseGateInit:
    def test_starts_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        assert e.current_phase == Phase.RESEARCH

    def test_research_entered(self):
        e = PhaseGateEnforcer("/tmp/test")
        assert e._phases[Phase.RESEARCH].entered is True

    def test_other_phases_not_entered(self):
        e = PhaseGateEnforcer("/tmp/test")
        assert e._phases[Phase.PLAN].entered is False
        assert e._phases[Phase.BUILD].entered is False
        assert e._phases[Phase.VERIFY].entered is False
        assert e._phases[Phase.SHIP].entered is False


def _do_research(e):
    """Helper: complete RESEARCH phase (3 web_search, 2 browse_web, 1 JSON artifact)."""
    e.record_tool_use("web_search")
    e.record_tool_use("web_search")
    e.record_tool_use("web_search")
    e.record_tool_use("browse_web")
    e.record_tool_use("browse_web")
    e.record_file_created("research.json")
    e.tick()


def _do_plan(e):
    """Helper: complete PLAN phase."""
    e.record_file_created("ARCHITECTURE.md")
    e.tick()


def _do_build(e):
    """Helper: complete BUILD phase (3 .py files)."""
    e.record_file_created("main.py")
    e.record_file_created("utils.py")
    e.record_file_created("test_main.py")
    e.tick()


def _do_verify(e):
    """Helper: complete VERIFY phase (tests pass + readme + requirements)."""
    e.record_command_output("pytest tests/", "5 passed in 1.2s")
    e.record_file_created("README.md")
    e.record_file_created("requirements.txt")
    e.tick()


def _do_ship(e):
    """Helper: complete SHIP phase (git init + commit)."""
    e.record_command_output("git init", "Initialized empty Git repository")
    e.record_command_output("git commit -m 'init'", "1 file changed")
    e.tick()


class TestResearchPhaseGate:
    """RESEARCH phase: must use >=3 web_search, >=2 browse_web, save JSON artifact."""

    def test_cannot_skip_research(self):
        """Without research tools, stays in RESEARCH forever."""
        e = PhaseGateEnforcer("/tmp/test")
        for _ in range(20):
            e.tick()
        assert e.current_phase == Phase.RESEARCH, "Must not skip research without research tools"

    def test_research_requires_enough_searches(self):
        """Must do >=3 web searches."""
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("web_search")  # only 1
        e.record_tool_use("browse_web")
        e.record_tool_use("browse_web")
        e.record_file_created("research.json")
        e.tick()
        assert e.current_phase == Phase.RESEARCH

    def test_research_requires_enough_browsing(self):
        """Must browse >=2 sites."""
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("web_search")
        e.record_tool_use("web_search")
        e.record_tool_use("web_search")
        e.record_tool_use("browse_web")  # only 1
        e.record_file_created("research.json")
        e.tick()
        assert e.current_phase == Phase.RESEARCH

    def test_research_requires_artifact(self):
        """Must save a JSON research artifact."""
        e = PhaseGateEnforcer("/tmp/test")
        e.record_tool_use("web_search")
        e.record_tool_use("web_search")
        e.record_tool_use("web_search")
        e.record_tool_use("browse_web")
        e.record_tool_use("browse_web")
        # No JSON artifact
        e.tick()
        assert e.current_phase == Phase.RESEARCH

    def test_research_advances_when_all_met(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        assert e.current_phase == Phase.PLAN

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


class TestPlanPhaseGate:
    """PLAN phase: must create spec/architecture document. NO escape hatch."""

    def test_research_advances_to_plan(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        assert e.current_phase == Phase.PLAN

    def test_plan_blocks_run_command(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        allowed, _ = e.is_tool_allowed("run_command")
        assert allowed is False

    def test_plan_allows_read_write_file(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        allowed, _ = e.is_tool_allowed("read_write_file")
        assert allowed is True

    def test_plan_allows_web_search_for_reference(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        allowed, _ = e.is_tool_allowed("web_search")
        assert allowed is True

    def test_plan_advances_with_spec_file(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        e.record_file_created("ARCHITECTURE.md")
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_plan_no_escape_hatch_10_iterations(self):
        """10+ iterations without spec file -> still blocked in PLAN."""
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        assert e.current_phase == Phase.PLAN
        for _ in range(10):
            e.tick()
        assert e.current_phase == Phase.PLAN, "PLAN must NOT have an escape hatch"

    def test_plan_no_escape_hatch_50_iterations(self):
        """50 iterations without spec -> still PLAN."""
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        for _ in range(50):
            e.tick()
        assert e.current_phase == Phase.PLAN

    def test_plan_advances_with_plan_md(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        e.record_file_created("plan.md")
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_plan_advances_with_spec_md(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        e.record_file_created("SPEC.md")
        e.tick()
        assert e.current_phase == Phase.BUILD


class TestBuildPhaseGate:
    """BUILD phase: must create >=3 Python files."""

    def _enter_build(self, e):
        _do_research(e)
        _do_plan(e)
        assert e.current_phase == Phase.BUILD

    def test_build_needs_python_files(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_build_advances_with_3_py_files(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.record_file_created("main.py")
        e.record_file_created("utils.py")
        e.record_file_created("app.py")
        e.tick()
        assert e.current_phase == Phase.VERIFY

    def test_build_not_enough_with_2_files(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.record_file_created("main.py")
        e.record_file_created("utils.py")
        e.tick()
        assert e.current_phase == Phase.BUILD

    def test_non_python_files_dont_count(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_build(e)
        e.record_file_created("README.md")
        e.record_file_created("config.yaml")
        e.record_file_created("data.json")
        e.tick()
        assert e.current_phase == Phase.BUILD


class TestVerifyPhaseGate:
    """VERIFY phase (merged TEST+VERIFY): tests must be RUN and PASS, README + requirements must exist."""

    def _enter_verify(self, e):
        _do_research(e)
        _do_plan(e)
        _do_build(e)
        assert e.current_phase == Phase.VERIFY

    def test_verify_needs_tests_run(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        e.tick()
        assert e.current_phase == Phase.VERIFY, "Must run tests to advance"

    def test_verify_needs_tests_passed(self):
        """Tests run but FAILED -> stay in VERIFY."""
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("pytest tests/", "FAILED 2 tests")
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        e.tick()
        assert e.current_phase == Phase.VERIFY, "Failed tests must not advance"
        assert e._phases[Phase.VERIFY].tests_run is True
        assert e._phases[Phase.VERIFY].test_passed is False

    def test_verify_needs_readme(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("pytest", "2 passed")
        e.record_file_created("requirements.txt")
        e.tick()
        assert e.current_phase == Phase.VERIFY

    def test_verify_needs_requirements(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("pytest", "2 passed")
        e.record_file_created("README.md")
        e.tick()
        assert e.current_phase == Phase.VERIFY

    def test_verify_advances_with_all(self):
        """Tests pass + README + requirements.txt -> advance to SHIP."""
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("pytest tests/", "5 passed in 1.2s")
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        e.tick()
        assert e.current_phase == Phase.SHIP

    def test_verify_requires_both_tests_run_and_passed(self):
        """Explicit test: VERIFY requires tests_run AND test_passed."""
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e._phases[Phase.VERIFY].tests_run = True
        e._phases[Phase.VERIFY].test_passed = False
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        e.tick()
        assert e.current_phase == Phase.VERIFY, "Must have both tests_run AND test_passed"

    def test_verify_detects_pytest_output(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("python -m pytest", "10 passed, 0 warnings")
        assert e._phases[Phase.VERIFY].tests_run is True
        assert e._phases[Phase.VERIFY].test_passed is True


class TestShipPhaseGate:
    """SHIP phase: must git init and git commit."""

    def _enter_ship(self, e):
        _do_research(e)
        _do_plan(e)
        _do_build(e)
        _do_verify(e)
        assert e.current_phase == Phase.SHIP

    def test_ship_blocks_without_git_init(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_ship(e)
        e.record_command_output("git commit -m 'init'", "1 file changed")
        e.tick()
        assert e.current_phase == Phase.SHIP

    def test_ship_blocks_without_git_commit(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_ship(e)
        e.record_command_output("git init", "Initialized")
        e.tick()
        assert e.current_phase == Phase.SHIP

    def test_ship_advances_with_both(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_ship(e)
        e.record_command_output("git init", "Initialized")
        e.record_command_output("git commit -m 'init'", "1 file changed")
        e.tick()
        assert e.current_phase == Phase.COMPLETE

    def test_ship_tool_restrictions(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_ship(e)
        allowed, _ = e.is_tool_allowed("run_command")
        assert allowed is True
        allowed, _ = e.is_tool_allowed("read_write_file")
        assert allowed is True
        allowed, _ = e.is_tool_allowed("web_search")
        assert allowed is False
        allowed, _ = e.is_tool_allowed("browse_web")
        assert allowed is False


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
        _do_research(e)
        _do_plan(e)
        e.record_file_created("main.py")
        e.record_file_created("app.py")
        e.record_file_created("lib.py")
        e.record_file_created("README.md")
        e.record_file_created("requirements.txt")
        e.record_command_output("pytest", "1 FAILED")
        can, blockers = e.can_complete()
        assert can is False
        assert any("pass" in b.lower() for b in blockers)

    def test_cannot_complete_without_ship(self):
        """Even with all phases done except SHIP, cannot complete."""
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        _do_plan(e)
        _do_build(e)
        _do_verify(e)
        assert e.current_phase == Phase.SHIP
        can, blockers = e.can_complete()
        assert can is False
        assert any("SHIP" in b for b in blockers)

    def test_full_lifecycle_can_complete(self):
        """Full happy path: RESEARCH -> PLAN -> BUILD -> VERIFY -> SHIP -> COMPLETE."""
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        assert e.current_phase == Phase.PLAN
        _do_plan(e)
        assert e.current_phase == Phase.BUILD
        _do_build(e)
        assert e.current_phase == Phase.VERIFY
        _do_verify(e)
        assert e.current_phase == Phase.SHIP
        _do_ship(e)
        assert e.current_phase == Phase.COMPLETE
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

    def test_plan_instruction(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        instr = e.get_phase_instruction()
        assert "PLAN" in instr
        assert "spec" in instr.lower() or "SPEC" in instr

    def test_build_instruction(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        _do_plan(e)
        instr = e.get_phase_instruction()
        assert "BUILD" in instr

    def test_verify_instruction(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        _do_plan(e)
        _do_build(e)
        instr = e.get_phase_instruction()
        assert "VERIFY" in instr
        assert "test" in instr.lower()

    def test_ship_instruction(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        _do_plan(e)
        _do_build(e)
        _do_verify(e)
        instr = e.get_phase_instruction()
        assert "SHIP" in instr
        assert "git" in instr.lower()


class TestToolBlocking:
    """Tests for is_tool_allowed phase enforcement."""

    def test_run_command_blocked_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        allowed, reason = e.is_tool_allowed("run_command")
        assert allowed is False
        assert "RESEARCH" in reason

    def test_git_blocked_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        allowed, _ = e.is_tool_allowed("git_operation")
        assert allowed is False

    def test_query_database_blocked_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        allowed, _ = e.is_tool_allowed("query_database")
        assert allowed is False


class TestBugFixResearchInstruction:
    """BUG 3: RESEARCH phase instruction must mention .json/.md only."""

    def test_research_instruction_mentions_json_md_only(self):
        e = PhaseGateEnforcer("/tmp/test")
        instruction = e.get_phase_instruction()
        assert ".json" in instruction
        assert ".md" in instruction
        assert "only create" in instruction.lower() or "only create" in instruction

    def test_browse_web_allowed_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        allowed, _ = e.is_tool_allowed("browse_web")
        assert allowed is True

    def test_web_search_allowed_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        allowed, _ = e.is_tool_allowed("web_search")
        assert allowed is True

    def test_read_write_file_allowed_in_research(self):
        e = PhaseGateEnforcer("/tmp/test")
        allowed, _ = e.is_tool_allowed("read_write_file")
        assert allowed is True

    def test_all_tools_allowed_in_build(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        _do_plan(e)
        assert e.current_phase == Phase.BUILD
        allowed, _ = e.is_tool_allowed("run_command")
        assert allowed is True
        allowed, _ = e.is_tool_allowed("git_operation")
        assert allowed is True

    def test_run_command_blocked_in_plan(self):
        e = PhaseGateEnforcer("/tmp/test")
        _do_research(e)
        assert e.current_phase == Phase.PLAN
        allowed, reason = e.is_tool_allowed("run_command")
        assert allowed is False
        assert "PLAN" in reason


class TestAntiSpoofing:
    """Tests that simple echo/fake commands don't defeat test gates."""

    def _enter_verify(self, e):
        _do_research(e)
        _do_plan(e)
        _do_build(e)
        assert e.current_phase == Phase.VERIFY

    def test_echo_passed_does_not_count(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output('echo "passed"', 'passed')
        assert e._phases[Phase.VERIFY].tests_run is False

    def test_echo_without_pytest_keyword_does_not_count(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output('echo "all tests passed"', 'all tests passed')
        assert e._phases[Phase.VERIFY].tests_run is False

    def test_real_pytest_counts(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("pytest tests/", "====== 5 passed in 1.2s ======")
        assert e._phases[Phase.VERIFY].tests_run is True
        assert e._phases[Phase.VERIFY].test_passed is True

    def test_real_pytest_failure_detected(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("pytest tests/", "2 passed, 1 FAILED")
        assert e._phases[Phase.VERIFY].tests_run is True
        assert e._phases[Phase.VERIFY].test_passed is False

    def test_python_m_pytest_counts(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("python -m pytest", "10 passed, 0 warnings")
        assert e._phases[Phase.VERIFY].tests_run is True
        assert e._phases[Phase.VERIFY].test_passed is True

    def test_unittest_counts(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("python -m unittest discover", "OK")
        assert e._phases[Phase.VERIFY].tests_run is True
        assert e._phases[Phase.VERIFY].test_passed is True

    def test_random_command_not_test(self):
        e = PhaseGateEnforcer("/tmp/test")
        self._enter_verify(e)
        e.record_command_output("python main.py", "Application started successfully")
        assert e._phases[Phase.VERIFY].tests_run is False


class TestSummary:
    def test_summary_structure(self):
        e = PhaseGateEnforcer("/tmp/test")
        s = e.get_summary()
        assert s["current_phase"] == "research"
        assert "phases" in s
        assert "research" in s["phases"]
        assert "total_iterations" in s