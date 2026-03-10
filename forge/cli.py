"""Forge CLI — command-line interface for the AI Agency Meta-Factory."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.status import Status

console = Console()


def run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _print_getting_started(output_path, blueprint=None):
    """Print a clear getting-started guide after agency generation."""
    agent_count = len(blueprint.all_agents) if blueprint else "?"
    team_count = len(blueprint.teams) if blueprint else "?"

    guide = (
        f"[bold green]🎉 Agency Generated Successfully![/bold green]\n\n"
        f"📁 Location: [cyan]{output_path}[/cyan]\n"
        f"👥 Teams: {team_count} | 🤖 Agents: {agent_count}\n\n"
        f"[bold]Quick Start:[/bold]\n\n"
        f"  [dim]1.[/dim] [cyan]cd {output_path}[/cyan]\n"
        f"  [dim]2.[/dim] [cyan]python test_agency.py[/cyan]        [dim]# Verify everything works[/dim]\n"
        f"  [dim]3.[/dim] [cyan]export OPENAI_API_KEY=sk-...[/cyan]  [dim]# Set your API key[/dim]\n"
        f"  [dim]4.[/dim] [cyan]python main.py[/cyan]               [dim]# Run interactively[/dim]\n"
        f"  [dim]5.[/dim] [cyan]uvicorn api_server:app --port 8000[/cyan]  [dim]# Start REST API[/dim]\n\n"
        f"[bold]API Endpoints:[/bold] (24 endpoints available)\n"
        f"  POST /api/task          [dim]Execute a task[/dim]\n"
        f"  POST /api/task/stream   [dim]Stream a task (SSE)[/dim]\n"
        f"  POST /api/plan          [dim]Plan a complex task[/dim]\n"
        f"  GET  /api/status        [dim]Agency status + metrics[/dim]\n"
        f"  GET  /api/analytics/revenue  [dim]ROI dashboard[/dim]\n"
        f"  GET  /api/costs         [dim]Cost tracking[/dim]\n"
        f"  GET  /health            [dim]Health check[/dim]\n\n"
        f"[bold]Docker:[/bold]\n"
        f"  [cyan]docker compose up --build[/cyan]  [dim]# Deploy as container[/dim]\n\n"
        f"[dim]Set AGENCY_API_KEY=your-secret to enable API authentication.[/dim]\n"
        f"[dim]Set FORGE_SMART_ROUTING=true to auto-optimize LLM costs.[/dim]"
    )

    console.print(Panel(guide, title="🔨 Forge — Getting Started", border_style="green"))


@click.group()
@click.version_option(version="0.1.0", prog_name="forge")
def main():
    """🔨 Forge — AI Agency Meta-Factory
    
    Generate complete, deployable AI agencies from domain descriptions.
    """
    pass


@main.command()
@click.argument("domain", required=False)
@click.option("--file", "-f", type=click.Path(exists=True), help="Read domain description from file")
@click.option("--output", "-o", type=click.Path(), default="generated", help="Output directory")
@click.option("--model", "-m", default=None, help="LLM model to use (default: from env or gpt-4)")
@click.option("--overwrite", is_flag=True, help="Overwrite existing agency")
@click.option("--api-key", envvar="OPENAI_API_KEY", help="OpenAI API key")
@click.option("--base-url", envvar="OPENAI_BASE_URL", help="OpenAI-compatible API base URL")
@click.option("--pack", "-p", type=click.Choice(["saas_support", "ecommerce", "real_estate"]), help="Use a pre-built domain pack (no API key needed)")
@click.option("--founder-mode", is_flag=True, help="Founder mode: let the AI decide agents instead of injecting mandatory archetypes")
@click.option("--force", is_flag=True, help="Generate agency even if quality score is below threshold")
def create(domain, file, output, model, overwrite, api_key, base_url, pack, founder_mode, force):
    """Create a new AI agency from a domain description.
    
    Provide a domain description as an argument or via --file.
    
    Examples:
    
        forge create "e-commerce customer support agency"
        
        forge create --file domain.txt --output ./my-agencies
        
        forge create "healthcare scheduling" --model gpt-4o
        
        forge create --pack saas_support
    """
    if pack:
        from forge.packs import create_from_pack
        from forge.core.archetypes import inject_archetypes
        from forge.generators.agency_generator import AgencyGenerator

        console.print(f"[bold cyan]📦 Using domain pack: {pack}[/bold cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Loading domain pack...", total=None)
            blueprint = create_from_pack(pack)
            progress.update(task, description="[green]✓ Domain pack loaded")

            if not founder_mode:
                progress.update(task, description="Injecting universal archetypes...")
                blueprint = inject_archetypes(blueprint)
                progress.update(task, description="[green]✓ Archetypes injected")

            progress.update(task, description="Generating agency code...")
            gen = AgencyGenerator(output_base=Path(output))
            try:
                output_path = gen.generate(blueprint, overwrite=overwrite)
            except FileExistsError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                console.print("Use --overwrite to replace.")
                sys.exit(1)
            progress.update(task, description="[green]✓ Agency generated")

            # Package runtime into generated agency
            progress.update(task, description="Packaging runtime...")
            import shutil
            runtime_src = Path(__file__).parent / "runtime"
            runtime_dst = output_path / "forge" / "runtime"
            forge_pkg = output_path / "forge"
            forge_pkg.mkdir(exist_ok=True)
            (forge_pkg / "__init__.py").write_text('"""Forge runtime — bundled with generated agency."""\n', encoding="utf-8")
            if runtime_dst.exists():
                shutil.rmtree(str(runtime_dst))
            shutil.copytree(str(runtime_src), str(runtime_dst), ignore=shutil.ignore_patterns("__pycache__"))
            progress.update(task, description="[green]✓ Runtime packaged")

        console.print(f"[bold green]✅ Agency generated at {output_path}[/bold green]")
        console.print(f"   Name: {blueprint.name}")
        console.print(f"   Agents: {len(blueprint.all_agents)}")
        console.print(f"   Teams: {len(blueprint.teams)}")
        _print_getting_started(output_path, blueprint)
        return

    # Get domain description
    if file:
        domain_text = Path(file).read_text(encoding="utf-8")
    elif domain:
        domain_text = domain
    else:
        console.print("[bold red]Error:[/bold red] Provide a domain description or use --file")
        console.print("\nUsage: forge create \"your domain description\"")
        console.print("   or: forge create --file domain.txt")
        sys.exit(1)

    if not domain_text.strip():
        console.print("[bold red]Error:[/bold red] Domain description is empty")
        sys.exit(1)

    from forge.core.engine import ForgeEngine

    engine = ForgeEngine(
        model=model,
        api_key=api_key,
        base_url=base_url,
        output_dir=Path(output),
    )

    try:
        blueprint, output_path = run_async(engine.create_agency(domain_text, overwrite=overwrite, inject_archetypes_flag=not founder_mode, force=force))
    except FileExistsError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print("Use --overwrite to replace the existing agency.")
        sys.exit(1)
    except Exception as e:
        from forge.core.engine import QualityGateError
        if isinstance(e, QualityGateError):
            console.print(f"[bold red]Quality Gate Failed:[/bold red] {e}")
        else:
            console.print(f"[bold red]Error:[/bold red] {e}")
            console.print(f"\n[dim]For debug output, set FORGE_DEBUG=1[/dim]")
        sys.exit(1)

    _print_getting_started(output_path, blueprint)


@main.command("list")
@click.option("--output", "-o", type=click.Path(), default="generated", help="Output directory to scan")
def list_agencies(output):
    """List previously generated agencies."""
    from forge.core.engine import ForgeEngine

    engine = ForgeEngine(output_dir=Path(output))

    agencies = run_async(engine.list_generated())

    if not agencies:
        console.print("[dim]No agencies generated yet. Use 'forge create' to get started.[/dim]")
        return

    table = Table(title="🏢 Generated Agencies")
    table.add_column("Name", style="cyan")
    table.add_column("Slug", style="dim")
    table.add_column("Teams", justify="right")
    table.add_column("Agents", justify="right")
    table.add_column("Path", style="dim")

    for a in agencies:
        table.add_row(
            a["name"],
            a["slug"],
            str(a["teams"]),
            str(a["agents"]),
            a["path"],
        )

    console.print(table)


@main.command()
@click.argument("agency_path", type=click.Path(exists=True))
@click.option("--port", "-p", default=8000, help="Port for the API server")
def run(agency_path, port):
    """Run a generated agency's API server.
    
    Example:
    
        forge run generated/my-agency --port 8080
    """
    import subprocess
    
    agency = Path(agency_path)
    api_server = agency / "api_server.py"
    
    if not api_server.exists():
        console.print(f"[bold red]Error:[/bold red] No api_server.py found in {agency}")
        sys.exit(1)

    console.print(f"[bold cyan]🚀 Starting agency server on port {port}...[/bold cyan]")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(agency),
    )


@main.command()
@click.argument("agency_path", type=click.Path(exists=True))
def inspect(agency_path):
    """Inspect a generated agency's blueprint.
    
    Example:
    
        forge inspect generated/my-agency
    """
    from forge.core.blueprint import AgencyBlueprint

    agency = Path(agency_path)
    blueprint_file = agency / "blueprint.json"

    if not blueprint_file.exists():
        console.print(f"[bold red]Error:[/bold red] No blueprint.json found in {agency}")
        sys.exit(1)

    bp = AgencyBlueprint.model_validate_json(blueprint_file.read_text(encoding="utf-8"))

    # Print detailed info
    console.print(Panel(
        f"[bold]{bp.name}[/bold]\n{bp.description}\n\n"
        f"[dim]Domain:[/dim] {bp.domain[:200]}",
        title="🏢 Agency Blueprint",
        border_style="cyan",
    ))

    # Teams table
    table = Table(title="Teams")
    table.add_column("Team", style="cyan")
    table.add_column("Lead", style="green")
    table.add_column("Agents", justify="right")
    table.add_column("Description")

    for team in bp.teams:
        lead_name = team.lead.name if team.lead else "—"
        table.add_row(team.name, lead_name, str(len(team.agents)), team.description[:60])

    console.print(table)

    # Agents table
    agent_table = Table(title="All Agents")
    agent_table.add_column("Name", style="cyan")
    agent_table.add_column("Role", style="green")
    agent_table.add_column("Title")
    agent_table.add_column("Tools", justify="right")

    for agent in bp.all_agents:
        agent_table.add_row(agent.name, agent.role.value, agent.title, str(len(agent.tools)))

    console.print(agent_table)

    # Tools
    if bp.all_tools:
        tool_table = Table(title="Tools")
        tool_table.add_column("Name", style="cyan")
        tool_table.add_column("Description")
        for t in bp.all_tools:
            tool_table.add_row(t.name, t.description[:80])
        console.print(tool_table)

    # Workflows
    if bp.workflows:
        wf_table = Table(title="Workflows")
        wf_table.add_column("Workflow", style="cyan")
        wf_table.add_column("Trigger", style="green")
        wf_table.add_column("Steps", justify="right")
        for wf in bp.workflows:
            wf_table.add_row(wf.name, wf.trigger, str(len(wf.steps)))
        console.print(wf_table)


@main.command()
@click.argument("agency_path", type=click.Path(exists=True))
def validate(agency_path):
    """Validate a generated agency's code and structure.

    Checks syntax, imports, file structure, and configuration.

    Example:

        forge validate generated/my-agency
    """
    from forge.generators.validator import AgencyValidator

    agency = Path(agency_path)
    validator = AgencyValidator()
    result = validator.validate(agency)

    console.print(result.summary())

    if result.errors:
        sys.exit(1)


@main.command()
def doctor():
    """Check system health and configuration.
    
    Verifies Python version, dependencies, API key, and more.
    """
    import platform

    table = Table(title="🩺 Forge Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # Python version
    py_ver = platform.python_version()
    py_ok = int(py_ver.split(".")[1]) >= 11
    table.add_row("Python version", "✅" if py_ok else "❌", f"{py_ver} {'(3.11+ required)' if not py_ok else ''}")

    # Dependencies
    deps = ["openai", "pydantic", "click", "jinja2", "fastapi", "rich"]
    for dep in deps:
        try:
            __import__(dep)
            table.add_row(f"  {dep}", "✅", "installed")
        except ImportError:
            table.add_row(f"  {dep}", "❌", "missing — run: pip install " + dep)

    # API key
    import os
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    table.add_row("OPENAI_API_KEY", "✅" if has_key else "⚠️", "configured" if has_key else "not set (needed for LLM-powered generation)")

    # Forge config
    try:
        from forge.config import get_config
        config = get_config()
        table.add_row("Forge config", "✅", f"model={config.model}")
    except Exception as e:
        table.add_row("Forge config", "⚠️", str(e)[:50])

    # Domain packs
    try:
        from forge.packs import AVAILABLE_PACKS
        table.add_row("Domain packs", "✅", f"{len(AVAILABLE_PACKS)} available")
    except Exception:
        table.add_row("Domain packs", "❌", "import failed")

    # Generated agencies
    generated = Path("generated")
    if generated.exists():
        agencies = [d for d in generated.iterdir() if d.is_dir() and (d / "blueprint.json").exists()]
        table.add_row("Generated agencies", "✅" if agencies else "—", f"{len(agencies)} found" if agencies else "none yet")
    else:
        table.add_row("Generated agencies", "—", "no 'generated/' directory")

    console.print(table)
    console.print("\n[dim]Run 'forge packs' to see available domain packs.[/dim]")
    console.print("[dim]Run 'forge create --pack saas_support' to generate your first agency.[/dim]")


@main.command("packs")
def list_packs():
    """List available pre-built domain packs."""
    from forge.packs import AVAILABLE_PACKS

    table = Table(title="📦 Available Domain Packs")
    table.add_column("Pack", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")

    for key, info in AVAILABLE_PACKS.items():
        table.add_row(key, info["name"], info["description"])

    console.print(table)
    console.print("\n[dim]Usage: forge create --pack <pack_name>[/dim]")


@main.command()
@click.argument("agency_path", type=click.Path(exists=True))
@click.option("--port", default=8000, help="Port to expose (default: 8000)")
@click.option("--name", default=None, help="Container name (defaults to agency directory name)")
@click.option("--detach", "-d", is_flag=True, help="Run container in background")
@click.option("--build-only", is_flag=True, help="Build image without running")
def deploy(agency_path, port, name, detach, build_only):
    """Deploy a generated agency as a Docker container.

    Builds a Docker image from the agency directory and runs it,
    making the API available on the specified port.

    Example:
        forge deploy ./my-agency
        forge deploy ./my-agency --port 9000 --detach
        forge deploy ./my-agency --build-only
    """
    import subprocess
    import shutil
    from pathlib import Path

    agency_dir = Path(agency_path).resolve()
    if not (agency_dir / "api_server.py").exists():
        click.secho(f"Error: {agency_dir} doesn't look like a generated agency (no api_server.py)", fg="red")
        raise SystemExit(1)

    if not shutil.which("docker"):
        click.secho("Error: Docker is not installed or not in PATH", fg="red")
        click.echo("Install Docker: https://docs.docker.com/get-docker/")
        raise SystemExit(1)

    container_name = name or agency_dir.name.lower().replace(" ", "-")
    image_name = f"forge-{container_name}"

    # Generate Dockerfile
    dockerfile_path = agency_dir / "Dockerfile"
    if not dockerfile_path.exists():
        click.echo("📝 Generating Dockerfile...")
        dockerfile_content = f"""FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*

# Copy agency code
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir openai pydantic fastapi uvicorn rich tiktoken 2>/dev/null || \\
    pip install --no-cache-dir openai pydantic fastapi uvicorn rich

# Install forge runtime if available
RUN if [ -d "forge" ]; then cd /app && pip install --no-cache-dir -e . 2>/dev/null || true; fi

EXPOSE {port}

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')" || exit 1

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "{port}"]
"""
        dockerfile_path.write_text(dockerfile_content)
        click.echo(f"  ✅ Dockerfile created at {dockerfile_path}")

    # Build Docker image
    with console.status(f"[bold cyan]🔨 Building Docker image: {image_name}[/bold cyan]") as status:
        result = subprocess.run(
            ["docker", "build", "-t", image_name, "."],
            cwd=str(agency_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[bold red]Build failed:[/bold red]\n{result.stderr}")
            raise SystemExit(1)
    console.print(f"  [green]✅ Image built: {image_name}[/green]")

    if build_only:
        click.echo(f"\nRun manually: docker run -p {port}:{port} -e OPENAI_API_KEY=$OPENAI_API_KEY {image_name}")
        return

    # Run container
    console.print(f"\n[bold cyan]🚀 Starting container: {container_name}[/bold cyan]")
    
    # Stop existing container if running
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)

    run_cmd = [
        "docker", "run",
        "--name", container_name,
        "-p", f"{port}:{port}",
    ]
    # Pass secrets via env-file to avoid leaking in ps aux
    import tempfile
    import stat
    env_fd, env_file_path = tempfile.mkstemp(prefix=".forge-env-", suffix=".env")
    env_file = Path(env_file_path)
    os.close(env_fd)  # Close fd, we'll write via Path
    env_lines = []
    for key in ("OPENAI_API_KEY", "AGENCY_API_KEY"):
        val = os.environ.get(key, "")
        if val:
            env_lines.append(f"{key}={val}")
    if env_lines:
        env_file.write_text("\n".join(env_lines) + "\n")
        os.chmod(env_file_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
        run_cmd.extend(["--env-file", str(env_file)])
    if detach:
        run_cmd.append("-d")
    run_cmd.append(image_name)

    try:
        if detach:
            result = subprocess.run(run_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                click.secho(f"Failed to start: {result.stderr}", fg="red")
                raise SystemExit(1)
            click.echo()
            click.secho(f"  ✅ Agency deployed!", fg="green", bold=True)
            click.echo(f"\n  🌐 API:        http://localhost:{port}")
            click.echo(f"  📋 Health:     http://localhost:{port}/health")
            click.echo(f"  📊 Status:     http://localhost:{port}/api/status")
            click.echo(f"  📡 Events:     http://localhost:{port}/api/events")
            click.echo(f"\n  Stop:  docker stop {container_name}")
            click.echo(f"  Logs:  docker logs -f {container_name}")
        else:
            click.echo(f"\n  🌐 Starting on http://localhost:{port}")
            click.echo(f"  Press Ctrl+C to stop\n")
            subprocess.run(run_cmd)
    finally:
        try:
            if env_file.exists():
                env_file.unlink()
        except OSError:
            pass  # Best-effort cleanup


@main.command()
@click.argument("agency_path", type=click.Path(exists=True), required=False)
@click.option("--port", default=8080, help="Dashboard port (default: 8080)")
@click.option("--api-url", default=None, help="Agency API URL (default: auto-detect)")
def dashboard(agency_path, port, api_url):
    """Launch the Forge web dashboard for monitoring an agency.

    If agency_path is provided, starts both the agency API and dashboard.
    If --api-url is provided, connects to an already-running agency.

    Example:
        forge dashboard ./my-agency
        forge dashboard --api-url http://localhost:8000
    """
    import subprocess
    import sys
    from pathlib import Path

    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
    except ImportError:
        click.secho("Error: FastAPI and uvicorn required. Run: pip install fastapi uvicorn", fg="red")
        raise SystemExit(1)

    from forge.dashboard.app import get_dashboard_html

    # Create a minimal FastAPI app that serves the dashboard
    app = FastAPI(title="Forge Dashboard")

    target_api = api_url or f"http://localhost:8000"

    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard():
        html = get_dashboard_html()
        # Inject the API base URL
        html = html.replace(
            "const API_BASE = window.location.origin;",
            f'const API_BASE = {json.dumps(target_api)};',
        )
        return HTMLResponse(content=html)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "forge-dashboard"}

    # If agency path provided, start the agency API in background
    agency_process = None
    if agency_path:
        agency_dir = Path(agency_path).resolve()
        if (agency_dir / "api_server.py").exists():
            click.echo(f"🚀 Starting agency API from {agency_dir}...")
            agency_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api_server:app",
                 "--host", "0.0.0.0", "--port", "8000"],
                cwd=str(agency_dir),
            )
            click.echo(f"  ✅ Agency API starting on http://localhost:8000")

    click.echo(f"\n📊 Forge Dashboard: http://localhost:{port}")
    click.echo(f"   Connected to: {target_api}")
    click.echo(f"   Press Ctrl+C to stop\n")

    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    finally:
        if agency_process:
            agency_process.terminate()


if __name__ == "__main__":
    main()
