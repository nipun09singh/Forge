"""Post-generation validator — verifies generated agency code is correct."""

from __future__ import annotations

import logging
import py_compile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: str  # "error", "warning"
    file: str
    message: str


@dataclass
class ValidationResult:
    """Result of validating a generated agency."""
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    files_checked: int = 0
    files_passed: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        lines = [
            f"Validation: {status}",
            f"Files checked: {self.files_checked} ({self.files_passed} passed)",
        ]
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
            for e in self.errors[:5]:
                lines.append(f"  ❌ {e.file}: {e.message}")
        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")
            for w in self.warnings[:5]:
                lines.append(f"  ⚠️ {w.file}: {w.message}")
        return "\n".join(lines)


class AgencyValidator:
    """
    Validates that a generated agency project is correct and runnable.

    Checks:
    1. All expected files exist
    2. Python files have valid syntax
    3. Key imports are resolvable
    4. Blueprint JSON is valid
    5. Requirements file is clean
    """

    EXPECTED_FILES = [
        "main.py",
        "api_server.py",
        "blueprint.json",
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
        "README.md",
    ]

    EXPECTED_DIRS = ["agents", "tools"]

    def validate(self, agency_path: Path) -> ValidationResult:
        """Validate a generated agency project."""
        issues: list[ValidationIssue] = []
        files_checked = 0
        files_passed = 0

        if not agency_path.exists():
            return ValidationResult(
                passed=False,
                issues=[ValidationIssue("error", str(agency_path), "Directory does not exist")],
            )

        # 1. Check expected files
        for filename in self.EXPECTED_FILES:
            filepath = agency_path / filename
            files_checked += 1
            if not filepath.exists():
                issues.append(ValidationIssue("error", filename, "Expected file is missing"))
            else:
                files_passed += 1

        # 2. Check expected directories
        for dirname in self.EXPECTED_DIRS:
            dirpath = agency_path / dirname
            if not dirpath.is_dir():
                issues.append(ValidationIssue("warning", dirname, "Expected directory is missing"))

        # 3. Syntax check all Python files
        for pyfile in agency_path.rglob("*.py"):
            rel = pyfile.relative_to(agency_path)
            files_checked += 1
            try:
                py_compile.compile(str(pyfile), doraise=True)
                files_passed += 1
            except py_compile.PyCompileError as e:
                issues.append(ValidationIssue("error", str(rel), f"Syntax error: {e}"))

        # 4. Validate blueprint.json
        bp_file = agency_path / "blueprint.json"
        if bp_file.exists():
            files_checked += 1
            try:
                import json
                data = json.loads(bp_file.read_text(encoding="utf-8"))
                if "name" not in data or "slug" not in data:
                    issues.append(ValidationIssue("error", "blueprint.json", "Missing required fields (name, slug)"))
                else:
                    files_passed += 1
            except json.JSONDecodeError as e:
                issues.append(ValidationIssue("error", "blueprint.json", f"Invalid JSON: {e}"))

        # 5. Check requirements.txt
        req_file = agency_path / "requirements.txt"
        if req_file.exists():
            content = req_file.read_text(encoding="utf-8")
            if "forge-agency" in content:
                issues.append(ValidationIssue("warning", "requirements.txt", "References 'forge-agency' pip package (runtime should be bundled)"))

        # 6. Check main.py has key imports
        main_file = agency_path / "main.py"
        if main_file.exists():
            content = main_file.read_text(encoding="utf-8")
            for required_import in ["Agency", "Agent", "Team"]:
                if required_import not in content:
                    issues.append(ValidationIssue("warning", "main.py", f"Missing import for '{required_import}'"))
            if "build_agency" not in content:
                issues.append(ValidationIssue("error", "main.py", "Missing build_agency() function"))

        # 7. Check agent files exist and are non-empty
        agents_dir = agency_path / "agents"
        if agents_dir.is_dir():
            agent_files = list(agents_dir.glob("agent_*.py"))
            if not agent_files:
                issues.append(ValidationIssue("warning", "agents/", "No agent modules generated"))
            for af in agent_files:
                if af.stat().st_size < 50:
                    issues.append(ValidationIssue("warning", str(af.relative_to(agency_path)), "Agent file appears empty"))

        # 8. Check tool files
        tools_dir = agency_path / "tools"
        if tools_dir.is_dir():
            tool_files = list(tools_dir.glob("tool_*.py"))
            for tf in tool_files:
                content = tf.read_text(encoding="utf-8")
                if "# TODO" in content and "forge.runtime.integrations" not in content:
                    issues.append(ValidationIssue("warning", str(tf.relative_to(agency_path)), "Tool is a stub (contains TODO, not using built-in integration)"))

        has_errors = any(i.severity == "error" for i in issues)
        return ValidationResult(
            passed=not has_errors,
            issues=issues,
            files_checked=files_checked,
            files_passed=files_passed,
        )
