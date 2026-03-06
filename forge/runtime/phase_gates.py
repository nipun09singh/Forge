"""Hard phase gates for the orchestrator agent loop.

Enforces that agents MUST complete each phase before advancing:
RESEARCH -> PLAN -> BUILD -> VERIFY -> SHIP

Phase completion is verified by checking concrete artifacts,
not by trusting the agent's self-report.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    """Orchestrator execution phases."""
    RESEARCH = "research"
    PLAN = "plan"
    BUILD = "build"
    VERIFY = "verify"
    SHIP = "ship"
    COMPLETE = "complete"


# Minimum requirements to exit each phase
PHASE_REQUIREMENTS = {
    Phase.RESEARCH: {
        "min_web_searches": 3,
        "min_sites_browsed": 2,
        "required_tools": ["browse_web", "web_search"],
        "description": "Research the domain, APIs, and requirements before building.",
    },
    Phase.PLAN: {
        "must_create_spec": True,
        "spec_patterns": ["spec", "plan", "architecture", "design", "ARCHITECTURE"],
        "description": "Create a project specification",
    },
    Phase.BUILD: {
        "min_files": 3,
        "required_extensions": [".py"],
        "description": "Create the project structure and implementation files",
    },
    Phase.VERIFY: {
        "must_run_tests": True,
        "must_have_readme": True,
        "must_have_requirements": True,
        "description": "Run tests (must pass), ensure README and requirements.txt exist",
    },
    Phase.SHIP: {
        "must_git_init": True,
        "must_git_commit": True,
        "description": "Initialize git repository and commit all files",
    },
}


@dataclass
class PhaseStatus:
    """Tracks completion status of a single phase."""
    phase: Phase
    entered: bool = False
    completed: bool = False
    iterations_in_phase: int = 0
    tools_used: set[str] = field(default_factory=set)
    files_created: list[str] = field(default_factory=list)
    tests_run: bool = False
    test_passed: bool = False
    web_searches: int = 0
    sites_browsed: int = 0
    research_artifact_saved: bool = False
    git_initialized: bool = False
    git_committed: bool = False


class PhaseGateEnforcer:
    """
    Enforces hard phase gates in the orchestrator loop.

    Instead of hoping the agent follows prompt instructions,
    this tracks what the agent HAS DONE and blocks phase transitions
    until requirements are met.
    """

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self._current_phase = Phase.RESEARCH
        self._phases: dict[Phase, PhaseStatus] = {
            p: PhaseStatus(phase=p) for p in Phase if p != Phase.COMPLETE
        }
        self._phases[Phase.RESEARCH].entered = True
        self._total_iterations = 0

    @property
    def current_phase(self) -> Phase:
        return self._current_phase

    def tick(self) -> None:
        """Called each orchestrator iteration."""
        self._total_iterations += 1
        status = self._phases[self._current_phase]
        status.iterations_in_phase += 1
        self._try_advance()

    def record_tool_use(self, tool_name: str) -> None:
        """Record that a tool was used in the current phase."""
        self._phases[self._current_phase].tools_used.add(tool_name)
        # Track research-specific counters
        if tool_name == "web_search":
            self._phases[Phase.RESEARCH].web_searches += 1
        elif tool_name == "browse_web":
            self._phases[Phase.RESEARCH].sites_browsed += 1
        # Detect test execution
        if tool_name == "run_command":
            self._phases[Phase.VERIFY].tools_used.add(tool_name)

    def is_tool_allowed(self, tool_name: str) -> tuple[bool, str]:
        """Check if a tool is appropriate for the current phase."""
        if self._current_phase == Phase.RESEARCH:
            allowed_in_research = {"browse_web", "web_search", "read_write_file"}
            if tool_name not in allowed_in_research:
                return False, f"Tool '{tool_name}' not allowed during RESEARCH phase. Use browse_web or web_search to research first."
        elif self._current_phase == Phase.PLAN:
            allowed_in_plan = {"read_write_file", "web_search", "browse_web"}
            if tool_name not in allowed_in_plan:
                return False, f"Tool '{tool_name}' not allowed during PLAN phase. Create your project specification first using read_write_file."
        elif self._current_phase == Phase.SHIP:
            allowed_in_ship = {"run_command", "read_write_file"}
            if tool_name not in allowed_in_ship:
                return False, f"Tool '{tool_name}' not allowed during SHIP phase. Use run_command for git operations."
        return True, ""

    def record_command_output(self, command: str, output: str) -> None:
        """Record command execution to detect test runs and git operations."""
        # Detect git operations
        if "git init" in command:
            self._phases[Phase.SHIP].git_initialized = True
        if "git commit" in command:
            self._phases[Phase.SHIP].git_committed = True

        # Require actual test framework command
        test_commands = ["pytest", "python -m pytest", "python -m unittest", "unittest"]
        is_test_command = any(tc in command for tc in test_commands)

        if not is_test_command:
            return  # Not a real test run

        self._phases[Phase.VERIFY].tests_run = True

        # Parse test results
        fail_indicators = ["FAILED", "ERRORS", "errors=", "failures="]
        pass_indicators = ["passed", "OK"]

        has_failures = any(f in output for f in fail_indicators)
        has_passes = any(p in output for p in pass_indicators)

        if has_passes and not has_failures:
            self._phases[Phase.VERIFY].test_passed = True
        else:
            self._phases[Phase.VERIFY].test_passed = False

    def record_file_created(self, filepath: str) -> None:
        """Record a file creation."""
        self._phases[self._current_phase].files_created.append(filepath)
        # Also record in BUILD phase regardless of current phase
        if filepath not in self._phases[Phase.BUILD].files_created:
            self._phases[Phase.BUILD].files_created.append(filepath)
        # Detect research artifact (JSON file saved during RESEARCH)
        if filepath.endswith(".json") and self._current_phase == Phase.RESEARCH:
            self._phases[Phase.RESEARCH].research_artifact_saved = True

    def _try_advance(self) -> None:
        """Try to advance to the next phase if current requirements are met."""
        if self._current_phase == Phase.COMPLETE:
            return

        status = self._phases[self._current_phase]
        reqs = PHASE_REQUIREMENTS[self._current_phase]

        if self._current_phase == Phase.RESEARCH:
            rs = self._phases[Phase.RESEARCH]
            has_searches = rs.web_searches >= reqs["min_web_searches"]
            has_browsed = rs.sites_browsed >= reqs["min_sites_browsed"]
            has_artifact = rs.research_artifact_saved
            if has_searches and has_browsed and has_artifact:
                self._advance_to(Phase.PLAN)

        elif self._current_phase == Phase.PLAN:
            # NO escape hatch -- must create a spec file
            spec_patterns = reqs["spec_patterns"]
            all_files = []
            for p_status in self._phases.values():
                all_files.extend(p_status.files_created)
            has_spec = any(
                any(pat.lower() in f.lower() for pat in spec_patterns)
                for f in all_files
            )
            if has_spec:
                self._advance_to(Phase.BUILD)

        elif self._current_phase == Phase.BUILD:
            has_files = len([f for f in status.files_created
                           if any(f.endswith(ext) for ext in reqs["required_extensions"])]) >= reqs["min_files"]
            if has_files:
                self._advance_to(Phase.VERIFY)

        elif self._current_phase == Phase.VERIFY:
            all_files = []
            for p_status in self._phases.values():
                all_files.extend(p_status.files_created)
            has_readme = any("readme" in f.lower() for f in all_files)
            has_requirements = any("requirements" in f.lower() for f in all_files)
            tests_ok = self._phases[Phase.VERIFY].tests_run and self._phases[Phase.VERIFY].test_passed
            if has_readme and has_requirements and tests_ok:
                self._advance_to(Phase.SHIP)

        elif self._current_phase == Phase.SHIP:
            ss = self._phases[Phase.SHIP]
            if ss.git_initialized and ss.git_committed:
                self._advance_to(Phase.COMPLETE)

    def _advance_to(self, phase: Phase) -> None:
        """Advance to the next phase."""
        self._phases[self._current_phase].completed = True
        self._current_phase = phase
        if phase != Phase.COMPLETE:
            self._phases[phase].entered = True
        logger.info(f"  Phase gate: advanced to {phase.value.upper()}")

    def get_phase_instruction(self) -> str:
        """Get the current phase instruction to inject into the conversation."""
        phase = self._current_phase
        if phase == Phase.COMPLETE:
            return ""
        status = self._phases[phase]

        header = f"\n=== CURRENT PHASE: {phase.value.upper()} (iteration {status.iterations_in_phase}) ===\n"

        if phase == Phase.RESEARCH:
            return (
                header +
                "You MUST research before building. Use browse_web or web_search to:\n"
                "- Read API documentation for any services needed\n"
                "- Understand best practices for this domain\n"
                "- Study similar projects and their architecture\n"
                "Requirements: >=3 web searches, >=2 sites browsed, save research artifact (JSON).\n"
                "You cannot proceed to PLAN until you've done research.\n"
            )
        elif phase == Phase.PLAN:
            return (
                header +
                "Create a PROJECT SPECIFICATION before building:\n"
                "- Architecture: what components, how they connect\n"
                "- File structure: list every file you'll create\n"
                "- Dependencies: what packages/APIs are needed\n"
                "- Acceptance criteria: how to verify it works\n"
                "Use read_write_file to create a spec document (e.g., SPEC.md or ARCHITECTURE.md).\n"
                "You MUST create this file. There is no escape hatch.\n"
            )
        elif phase == Phase.BUILD:
            return (
                header +
                "Now BUILD the project. Create all source files using read_write_file.\n"
                "- Create proper project structure\n"
                "- Implement all required features\n"
                "- Install dependencies with run_command\n"
                f"- Must create >=3 .py files\n"
                f"Files created so far: {len(status.files_created)}\n"
            )
        elif phase == Phase.VERIFY:
            all_files = []
            for p_status in self._phases.values():
                all_files.extend(p_status.files_created)
            missing = []
            if not any("readme" in f.lower() for f in all_files):
                missing.append("README.md")
            if not any("requirements" in f.lower() for f in all_files):
                missing.append("requirements.txt")
            tests_info = ""
            if not self._phases[Phase.VERIFY].tests_run:
                tests_info = "- You MUST run tests (pytest or unittest)\n"
            elif not self._phases[Phase.VERIFY].test_passed:
                tests_info = "- Tests ran but FAILED. Fix and re-run.\n"
            else:
                tests_info = "- Tests passed\n"
            return (
                header +
                "Verification phase: run tests and ensure docs exist.\n" +
                tests_info +
                (f"Missing required files: {', '.join(missing)}\n" if missing else "") +
                "- Ensure README has setup instructions\n"
                "- Ensure requirements.txt lists all dependencies\n"
            )
        elif phase == Phase.SHIP:
            return (
                header +
                "SHIP phase: prepare for delivery.\n"
                "- Initialize git repository: run_command('git init')\n"
                "- Stage and commit all files\n"
                "- Use run_command and read_write_file only.\n"
            )
        return ""

    def can_complete(self) -> tuple[bool, list[str]]:
        """Check if all phases are complete enough to accept DONE."""
        blockers = []

        if not self._phases[Phase.RESEARCH].completed:
            blockers.append("RESEARCH phase not completed")

        if not self._phases[Phase.PLAN].completed:
            blockers.append("PLAN phase not completed")

        build_status = self._phases[Phase.BUILD]
        py_files = [f for f in build_status.files_created if f.endswith(".py")]
        if len(py_files) < 3:
            blockers.append(f"BUILD phase incomplete -- only {len(py_files)} Python files created (need >=3)")

        if not self._phases[Phase.VERIFY].tests_run:
            blockers.append("VERIFY phase not completed -- must run tests before completing")
        elif not self._phases[Phase.VERIFY].test_passed:
            blockers.append("VERIFY phase not passed -- tests must pass before completing")

        all_files = []
        for p_status in self._phases.values():
            all_files.extend(p_status.files_created)
        if not any("readme" in f.lower() for f in all_files):
            blockers.append("VERIFY: Missing README.md")
        if not any("requirements" in f.lower() for f in all_files):
            blockers.append("VERIFY: Missing requirements.txt")

        if not self._phases[Phase.SHIP].git_initialized:
            blockers.append("SHIP phase not completed -- must initialize git repository")
        if not self._phases[Phase.SHIP].git_committed:
            blockers.append("SHIP phase not completed -- must commit files to git")

        return (len(blockers) == 0, blockers)

    def get_blocker_feedback(self) -> str:
        """Get feedback message about what's blocking completion."""
        can_done, blockers = self.can_complete()
        if can_done:
            return ""
        return (
            "You cannot complete yet. The following phase requirements are unmet:\n" +
            "\n".join(f"  - {b}" for b in blockers) +
            "\n\nPlease address these before saying DONE."
        )

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of phase progress."""
        return {
            "current_phase": self._current_phase.value,
            "total_iterations": self._total_iterations,
            "phases": {
                p.value: {
                    "entered": s.entered,
                    "completed": s.completed,
                    "iterations": s.iterations_in_phase,
                    "tools_used": list(s.tools_used),
                    "files_created": len(s.files_created),
                    "tests_run": s.tests_run,
                }
                for p, s in self._phases.items()
            },
        }