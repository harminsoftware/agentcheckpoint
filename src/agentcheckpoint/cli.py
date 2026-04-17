"""CLI for AgentCheckpoint — list, inspect, resume, and manage checkpoint runs."""

from __future__ import annotations

import json
import sys

import click

from agentcheckpoint.storage.local import LocalStorageBackend


def _get_storage(storage_path: str) -> LocalStorageBackend:
    return LocalStorageBackend(base_path=storage_path)


@click.group()
@click.option(
    "--storage-path",
    default="./checkpoints",
    envvar="AGENTCHECKPOINT_STORAGE_PATH",
    help="Path to checkpoint storage directory",
)
@click.pass_context
def cli(ctx, storage_path):
    """AgentCheckpoint — Transparent checkpoint & replay for AI agents."""
    ctx.ensure_object(dict)
    ctx.obj["storage_path"] = storage_path


@cli.command()
@click.pass_context
def list(ctx):
    """List all checkpoint runs."""
    storage = _get_storage(ctx.obj["storage_path"])
    runs = storage.list_runs()

    if not runs:
        click.echo("No checkpoint runs found.")
        return

    # Header
    click.echo(f"{'RUN ID':<14} {'STATUS':<10} {'STEPS':<7} {'FRAMEWORK':<12} {'UPDATED'}")
    click.echo("─" * 70)

    for run in runs:
        status_color = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
        }.get(run.status, "white")

        click.echo(
            f"{run.run_id:<14} "
            f"{click.style(run.status, fg=status_color):<19} "
            f"{run.total_steps:<7} "
            f"{run.framework:<12} "
            f"{run.updated_at[:19]}"
        )

    click.echo(f"\n{len(runs)} run(s) total")


@cli.command()
@click.argument("run_id")
@click.option("--step", type=int, default=None, help="Inspect a specific step")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def inspect(ctx, run_id, step, json_output):
    """Inspect a run's steps or a specific step's state."""
    from agentcheckpoint.resume import inspect_run

    try:
        result = inspect_run(
            run_id=run_id,
            step=step,
            storage_path=ctx.obj["storage_path"],
        )
    except FileNotFoundError:
        click.echo(f"Run not found: {run_id}", err=True)
        sys.exit(1)

    if step is None:
        # List steps
        if not result:
            click.echo(f"No steps found for run: {run_id}")
            return

        click.echo(f"Run: {run_id}")
        click.echo(f"{'STEP':<7} {'SIZE':<10} {'CHECKSUM':<18} {'TIMESTAMP'}")
        click.echo("─" * 60)

        for s in result:
            size = f"{s.size_bytes:,}B"
            error_marker = " ⚠" if s.has_error else ""
            click.echo(f"{s.step_number:<7} {size:<10} {s.checksum:<18} {s.timestamp[:19]}{error_marker}")

        click.echo(f"\n{len(result)} step(s)")
    else:
        # Show state at step
        if json_output:
            click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            click.echo(f"Run: {result.run_id}, Step: {result.step_number}")
            click.echo(f"Timestamp: {result.timestamp}")
            click.echo(f"Messages: {result.message_count}")
            click.echo(f"Tool Calls: {result.tool_call_count}")
            click.echo(f"Variables: {len(result.variables)} keys")
            if result.has_error:
                click.echo(click.style(f"\nError: {result.error.error_type}", fg="red"))
                click.echo(f"  {result.error.message}")

            if result.messages:
                click.echo("\n─── Messages ───")
                for msg in result.messages[-5:]:  # Show last 5
                    role = msg.get("role", "?")
                    content = str(msg.get("content", ""))[:200]
                    click.echo(f"  [{role}] {content}")

            if result.tool_calls:
                click.echo("\n─── Tool Calls ───")
                for tc in result.tool_calls[-5:]:
                    name = tc.get("tool_name", "?")
                    click.echo(f"  → {name}")


@cli.command()
@click.argument("run_id")
@click.option("--step", type=int, default=None, help="Resume from a specific step")
@click.option("--no-verify", is_flag=True, help="Skip checksum verification")
@click.pass_context
def resume(ctx, run_id, step, no_verify):
    """Resume a run from the last checkpoint (or a specific step)."""
    from agentcheckpoint.resume import resume as resume_fn

    try:
        result = resume_fn(
            run_id=run_id,
            step=step,
            verify_checksum=not no_verify,
            storage_path=ctx.obj["storage_path"],
        )
    except Exception as e:
        click.echo(f"Resume failed: {e}", err=True)
        sys.exit(1)

    click.echo(f"✓ Resumed run: {result.run_id}")
    click.echo(f"  Step: {result.step_number}")
    click.echo(f"  Messages: {len(result.messages)}")
    click.echo(f"  Tool Calls: {len(result.tool_calls)}")
    click.echo(f"  Variables: {len(result.variables)} keys")

    if result.error:
        click.echo(click.style(f"\n  Last error: {result.error.error_type}: {result.error.message}", fg="yellow"))

    click.echo("\nCheckpoint context is ready. Use result.context to continue the run.")


@cli.command()
@click.argument("run_id")
@click.confirmation_option(prompt="Are you sure you want to delete this run?")
@click.pass_context
def delete(ctx, run_id):
    """Delete all checkpoints for a run."""
    storage = _get_storage(ctx.obj["storage_path"])

    if not storage.run_exists(run_id):
        click.echo(f"Run not found: {run_id}", err=True)
        sys.exit(1)

    steps = storage.list_steps(run_id)
    storage.delete_run(run_id)
    click.echo(f"✓ Deleted run {run_id} ({len(steps)} steps)")


@cli.command()
@click.pass_context
def cleanup(ctx):
    """Remove incomplete temporary files from interrupted writes."""
    storage = _get_storage(ctx.obj["storage_path"])
    count = storage.cleanup_temp_files()
    click.echo(f"✓ Removed {count} temp file(s)")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Dashboard host")
@click.option("--port", default=8585, type=int, help="Dashboard port")
@click.pass_context
def dashboard(ctx, host, port):
    """Launch the replay dashboard."""
    try:
        import uvicorn
        from agentcheckpoint.dashboard.api.app import create_app
    except ImportError:
        click.echo(
            "Dashboard dependencies not installed. "
            "Install with: pip install agentcheckpoint[dashboard]",
            err=True,
        )
        sys.exit(1)

    app = create_app(storage_path=ctx.obj["storage_path"])
    click.echo(f"Starting dashboard at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli()
