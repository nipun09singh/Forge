"""Hard phase gates for the orchestrator agent loop.

Enforces that agents MUST complete each phase before advancing:
RESEARCH → BUILD → TEST → VERIFY

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
    BUILD = "build"
    TEST = "test"
    VERIFY = "verify"
    COMPLETE = "complete"


# Minimum requirements to exit each phase
PHASE_REQUIREMENTS = {
    Phase.RESEARCH: {
        "min_iterations": 2,
        "required_tools": ["browse_web", "web_search"],  # Must use at least one
        "description": "Research the domain, APIs, and requirements before building",
    },
    Phase.BUILD: {
        "min_files": 2,
        "required_extensions": [".py"],  # Must create at least one Python file
        "description": "Create the project structure and implementation files",
    },
    Phase.TEST: {
        "must_run_tests": True,
        "test_patterns": ["test_", "_test.py", "pytest", "unittest"],
        "description": "Write and run tests. Fix failures before proceeding.",
    },
    Phase.VERIFY: {
        "must_have_readme": True,
        "must_have_requirements": True,
        "description": "Add documentation, requirements.txt, and verify quality",
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


class PhaseGateEnforcer:
    """
    Enforces hard phase gates in the orchestrator loop.
    
    Instead of hoping the agent follows prompt instructions,
    this tracks what the agent HAS DONE and blocks phase transitions
    until requirements are met.
    
    Usage:
        enforcer = PhaseGateEnforcer(project_dir)
        
        # In orchestrator loop:
        phase_msg = enforcer.get_phase_instruction()  # What to tell the agent
        enforcer.record_tool_use(tool_name)            # After each tool call
        enforcer.record_file_created(filename)         # After each file creation
        
        # Before accepting DONE:
        can_complete, blockers = enforcer.can_complete()
        if not can_complete:
            # Force agent back to incomplete phases
            feedback = enforcer.get_blocker_feedback()
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
        # Detect test execution
        if tool_name == "run_command":
            self._phases[Phase.TEST].tools_used.add(tool_name)

    def is_tool_allowed(self, tool_name: str) -> tuple[bool, str]:
        """Check if a tool is appropriate for the current phase.
        
        Returns (allowed, reason). Blocks tools that would skip phases:
        - RESEARCH: only browse_web, web_search, read_write_file (for notes)
        - BUILD: no restrictions (needs all tools to create project)
        - TEST: no restrictions (needs run_command for tests)
        - VERIFY: no restrictions
        """
        if self._current_phase == Phase.RESEARCH:
            # During research, block build-only tools to enforce actual research
            blocked_in_research = {"run_command", "git_operation", "query_database"}
            if tool_name in blocked_in_research:
                return False, f"Tool '{tool_name}' not allowed during RESEARCH phase. Use browse_web or web_search to research first."
        return True, ""

    def record_command_output(self, command: str, output: str) -> None:
        """Record command execution to detect test runs.
        
        Uses strict matching: command must contain pytest/unittest to count.
        Simple 'echo passed' does not satisfy the test gate.
        """
        # Require actual test framework command — not just 'passed' in output
        test_commands = ["pytest", "python -m pytest", "python -m unittest", "unittest"]
        is_test_command = any(tc in command for tc in test_commands)
        
        if not is_test_command:
            return  # Not a real test run
        
        self._phases[Phase.TEST].tests_run = True
        
        # Parse test results — require explicit pass pattern from test framework
        fail_indicators = ["FAILED", "ERRORS", "errors=", "failures="]
        pass_indicators = ["passed", "OK"]
        
        has_failures = any(f in output for f in fail_indicators)
        has_passes = any(p in output for p in pass_indicators)
        
        if has_passes and not has_failures:
            self._phases[Phase.TEST].test_passed = True
        else:
            self._phases[Phase.TEST].test_passed = False

    def record_file_created(self, filepath: str) -> None:
        """Record a file creation."""
        self._phases[self._current_phase].files_created.append(filepath)
        # Also record in BUILD phase regardless of current phase
        if filepath not in self._phases[Phase.BUILD].files_created:
            self._phases[Phase.BUILD].files_created.append(filepath)

    def _try_advance(self) -> None:
        """Try to advance to the next phase if current requirements are met."""
        if self._current_phase == Phase.COMPLETE:
            return

        status = self._phases[self._current_phase]
        reqs = PHASE_REQUIREMENTS[self._current_phase]

        if self._current_phase == Phase.RESEARCH:
            research_tools = reqs["required_tools"]
            used_research = any(t in status.tools_used for t in research_tools)
            if status.iterations_in_phase >= reqs["min_iterations"] and used_research:
                self._advance_to(Phase.BUILD)

        elif self._current_phase == Phase.BUILD:
            has_files = len([f for f in status.files_created 
                           if any(f.endswith(ext) for ext in reqs["required_extensions"])]) >= reqs["min_files"]
            if has_files:
                self._advance_to(Phase.TEST)

        elif self._current_phase == Phase.TEST:
            if status.tests_run and status.test_passed:
                self._advance_to(Phase.VERIFY)

        elif self._current_phase == Phase.VERIFY:
            all_files = []
            for p_status in self._phases.values():
                all_files.extend(p_status.files_created)
            has_readme = any("readme" in f.lower() for f in all_files)
            has_requirements = any("requirements" in f.lower() for f in all_files)
            if has_readme and has_requirements:
                status.completed = True

    def _advance_to(self, phase: Phase) -> None:
        """Advance to the next phase."""
        self._phases[self._current_phase].completed = True
        self._current_phase = phase
        self._phases[phase].entered = True
        logger.info(f"  📋 Phase gate: advanced to {phase.value.upper()}")

    def get_phase_instruction(self) -> str:
        """Get the current phase instruction to inject into the conversation."""
        phase = self._current_phase
        status = self._phases[phase]
        reqs = PHASE_REQUIREMENTS[phase]

        header = f"\n═══ CURRENT PHASE: {phase.value.upper()} (iteration {status.iterations_in_phase}) ═══\n"

        if phase == Phase.RESEARCH:
            return (
                header +
                "You MUST research before building. Use browse_web or web_search to:\n"
                "- Read API documentation for any services needed\n"
                "- Understand best practices for this domain\n"
                "- Study similar projects and their architecture\n"
                "You cannot proceed to BUILD until you've done research.\n"
            )
        elif phase == Phase.BUILD:
            return (
                header +
                "Now BUILD the project. Create all source files using read_write_file.\n"
                "- Create proper project structure\n"
                "- Implement all required features\n"
                "- Install dependencies with run_command\n"
                f"Files created so far: {len(status.files_created)}\n"
            )
        elif phase == Phase.TEST:
            return (
                header +
                "You MUST write and run tests before completing.\n"
                "- Create test files (test_*.py)\n"
                "- Run tests with run_command (pytest or unittest)\n"
                "- Fix any failures\n"
                "You cannot mark DONE until tests pass.\n"
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
            return (
                header +
                "Final verification phase.\n" +
                (f"Missing required files: {', '.join(missing)}\n" if missing else "") +
                "- Ensure README has setup instructions\n"
                "- Ensure requirements.txt lists all dependencies\n"
                "- Review code quality\n"
                "When everything is ready, say DONE.\n"
            )
        return ""

    def can_complete(self) -> tuple[bool, list[str]]:
        """Check if all phases are complete enough to accept DONE."""
        blockers = []

        if not self._phases[Phase.RESEARCH].completed:
            blockers.append("RESEARCH phase not completed — must research before building")

        build_status = self._phases[Phase.BUILD]
        py_files = [f for f in build_status.files_created if f.endswith(".py")]
        if len(py_files) < 2:
            blockers.append(f"BUILD phase incomplete — only {len(py_files)} Python files created (need ≥2)")

        if not self._phases[Phase.TEST].tests_run:
            blockers.append("TEST phase not completed — must run tests before completing")
        elif not self._phases[Phase.TEST].test_passed:
            blockers.append("TEST phase not passed — tests must pass before completing")

        all_files = []
        for p_status in self._phases.values():
            all_files.extend(p_status.files_created)
        if not any("readme" in f.lower() for f in all_files):
            blockers.append("VERIFY: Missing README.md")
        if not any("requirements" in f.lower() for f in all_files):
            blockers.append("VERIFY: Missing requirements.txt")

        return (len(blockers) == 0, blockers)

    def get_blocker_feedback(self) -> str:
        """Get feedback message about what's blocking completion."""
        can_done, blockers = self.can_complete()
        if can_done:
            return ""
        return (
            "⚠️ You cannot complete yet. The following phase requirements are unmet:\n" +
            "\n".join(f"  • {b}" for b in blockers) +
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
