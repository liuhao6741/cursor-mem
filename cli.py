"""CLI entry point — `cursor-mem` command."""

from __future__ import annotations

import json
import sys

import click

from cursor_mem.config import Config, DATA_DIR


@click.group()
@click.version_option(package_name="cursor-mem")
def main():
    """cursor-mem — persistent memory for Cursor IDE."""
    pass


# ---------------------------------------------------------------------------
# install / uninstall
# ---------------------------------------------------------------------------

@main.command()
@click.option("--global", "global_install", is_flag=True, help="Install hooks globally (~/.cursor/)")
def install(global_install: bool):
    """Install hooks, start worker, and register MCP server."""
    from cursor_mem.installer import install_hooks, register_mcp, start_worker

    scope = "global" if global_install else "project"
    click.echo(f"Installing cursor-mem ({scope})...")

    hooks_path = install_hooks(global_install=global_install)
    click.echo(f"  [ok] Hooks installed: {hooks_path}")

    mcp_path = register_mcp()
    click.echo(f"  [ok] MCP server registered: {mcp_path}")

    pid = start_worker()
    click.echo(f"  [ok] Worker started (PID {pid})")

    cfg = Config.load()
    cfg.save()
    click.echo(f"  [ok] Config saved: {DATA_DIR / 'config.json'}")

    click.echo()
    click.echo("Done! Restart Cursor to activate hooks.")
    click.echo(f"Web viewer: http://127.0.0.1:{cfg.port}")


@main.command()
@click.option("--global", "global_install", is_flag=True)
def uninstall(global_install: bool):
    """Remove hooks, stop worker, and unregister MCP."""
    from cursor_mem.installer import uninstall_hooks, unregister_mcp, stop_worker

    uninstall_hooks(global_install=global_install)
    click.echo("  [ok] Hooks removed")

    unregister_mcp()
    click.echo("  [ok] MCP server unregistered")

    stop_worker()
    click.echo("  [ok] Worker stopped")

    click.echo("Done! Restart Cursor to deactivate.")


# ---------------------------------------------------------------------------
# Worker management
# ---------------------------------------------------------------------------

@main.command()
def start():
    """Start the worker service."""
    from cursor_mem.installer import start_worker, is_worker_running

    if is_worker_running():
        click.echo("Worker is already running.")
        return

    pid = start_worker()
    click.echo(f"Worker started (PID {pid})")


@main.command()
def stop():
    """Stop the worker service."""
    from cursor_mem.installer import stop_worker

    if stop_worker():
        click.echo("Worker stopped.")
    else:
        click.echo("Worker is not running.")


@main.command()
def restart():
    """Restart the worker service."""
    from cursor_mem.installer import stop_worker, start_worker

    stop_worker()
    pid = start_worker()
    click.echo(f"Worker restarted (PID {pid})")


@main.command()
def status():
    """Show worker status and statistics."""
    from cursor_mem.installer import is_worker_running, _read_pid
    from cursor_mem.config import Config

    cfg = Config.load()
    running = is_worker_running()
    pid = _read_pid()

    click.echo("cursor-mem status")
    click.echo(f"  Worker:    {'running' if running else 'stopped'}" + (f" (PID {pid})" if running else ""))
    click.echo(f"  Port:      {cfg.port}")
    click.echo(f"  Data dir:  {DATA_DIR}")
    click.echo(f"  AI:        {'enabled' if cfg.ai.enabled else 'disabled'}")

    if running:
        try:
            from urllib.request import urlopen
            import json as _json
            resp = urlopen(f"http://127.0.0.1:{cfg.port}/api/stats", timeout=2)
            stats = _json.loads(resp.read().decode())
            click.echo(f"  Sessions:  {stats.get('sessions_total', 0)} total, {stats.get('sessions_active', 0)} active")
            click.echo(f"  Observations: {stats.get('total_observations', 0)}")
        except Exception:
            click.echo("  (could not fetch stats)")


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

@main.group("config")
def config_group():
    """Manage configuration."""
    pass


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value (e.g. 'ai.enabled true')."""
    cfg = Config.load()
    cfg.set_nested(key, value)
    cfg.save()
    click.echo(f"Set {key} = {value}")


@config_group.command("get")
@click.argument("key", required=False)
def config_get(key: str | None):
    """Show configuration (or a specific key)."""
    from dataclasses import asdict

    cfg = Config.load()
    d = asdict(cfg)

    if key:
        parts = key.split(".")
        val = d
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p, "<not found>")
            else:
                val = "<not found>"
                break
        click.echo(f"{key} = {val}")
    else:
        click.echo(json.dumps(d, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Data management (Phase 3)
# ---------------------------------------------------------------------------

@main.group("data")
def data_group():
    """Manage stored data."""
    pass


@data_group.command("stats")
@click.option("--project", default=None, help="Filter by project name")
def data_stats(project: str | None):
    """Show storage statistics."""
    from cursor_mem.storage.database import init_db
    from cursor_mem.storage.session_store import get_session_stats, get_recent_sessions

    conn = init_db()
    stats = get_session_stats(conn, project=project)
    click.echo(f"Sessions:      {stats['sessions_total']} ({stats['sessions_active']} active, {stats['sessions_completed']} completed)")
    click.echo(f"Observations:  {stats['total_observations']}")

    sessions = get_recent_sessions(conn, project=project, limit=100)
    projects = set(s["project"] for s in sessions)
    click.echo(f"Projects:      {', '.join(sorted(projects)) if projects else '(none)'}")
    conn.close()


@data_group.command("cleanup")
@click.option("--keep-days", default=30, help="Delete sessions older than N days")
@click.option("--project", default=None, help="Filter by project name")
@click.confirmation_option(prompt="Delete old sessions?")
def data_cleanup(keep_days: int, project: str | None):
    """Delete old completed sessions."""
    from cursor_mem.storage.database import init_db
    from cursor_mem.storage.session_store import delete_old_sessions

    conn = init_db()
    deleted = delete_old_sessions(conn, keep_days=keep_days, project=project)
    click.echo(f"Deleted {deleted} session(s) older than {keep_days} days.")
    conn.close()


@data_group.command("export")
@click.argument("output", default="cursor-mem-export.json")
@click.option("--project", default=None, help="Filter by project name")
def data_export(output: str, project: str | None):
    """Export all data to a JSON file."""
    from cursor_mem.storage.database import init_db
    from cursor_mem.storage.session_store import get_recent_sessions
    from cursor_mem.storage.observation_store import get_observations_for_session

    conn = init_db()
    sessions = get_recent_sessions(conn, project=project, limit=10000)
    export_data = []
    for sess in sessions:
        obs = get_observations_for_session(conn, sess["id"])
        export_data.append({"session": sess, "observations": obs})
    conn.close()

    with open(output, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
    click.echo(f"Exported {len(sessions)} sessions to {output}")


@data_group.command("projects")
def data_projects():
    """List all known projects."""
    from cursor_mem.storage.database import init_db
    from cursor_mem.storage.session_store import get_recent_sessions, get_session_stats

    conn = init_db()
    sessions = get_recent_sessions(conn, limit=10000)
    projects: dict[str, int] = {}
    for s in sessions:
        projects[s["project"]] = projects.get(s["project"], 0) + 1

    if not projects:
        click.echo("No projects found.")
        return

    click.echo(f"{'Project':<30} {'Sessions':>10}")
    click.echo("-" * 42)
    for name, count in sorted(projects.items(), key=lambda x: -x[1]):
        click.echo(f"{name:<30} {count:>10}")
    conn.close()


if __name__ == "__main__":
    main()
