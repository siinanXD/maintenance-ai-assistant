"""Flask CLI commands for the maintenance agent."""

from __future__ import annotations

import json

import click

from app.agent.evals import evaluate_tool_selection
from app.agent.tools import TOOL_REGISTRY
from app.models import Role, User


@click.group("agent")
def agent_cli():
    """Inspect and evaluate the tool-using maintenance agent."""


@agent_cli.command("tools")
def list_tools_command():
    """Print the registered agent tools."""
    for spec in TOOL_REGISTRY.values():
        flags = []
        if spec.requires_confirmation:
            flags.append("confirm")
        if spec.write:
            flags.append("write")
        permission = ":".join(spec.permission) if spec.permission else "-"
        click.echo(f"{spec.name:28} permission={permission:20} {' '.join(flags)}")


@agent_cli.command("eval-tools")
@click.option("--username", default="", help="Evaluate with this user's permissions.")
@click.option("--as-json", is_flag=True, help="Print the full JSON report.")
def eval_tools_command(username, as_json):
    """Run the golden tool-selection cases with the configured provider."""
    user = None
    if username:
        user = User.query.filter_by(username=username).first()
        if user is None:
            raise click.ClickException(f"User not found: {username}")
    if user is None:
        user = User.query.filter_by(role=Role.MASTER_ADMIN).order_by(User.id.asc()).first()
    if user is None:
        raise click.ClickException("No master admin user available; pass --username")
    report = evaluate_tool_selection(user)
    if as_json:
        click.echo(json.dumps(report, ensure_ascii=True, indent=2))
        return
    click.echo(
        f"provider={report['provider']} accuracy={report['accuracy']} "
        f"({report['correct']}/{report['total']}) tools={report['tool_count']}"
    )
    for miss in report["misses"]:
        click.echo(
            f"MISS expected={miss['expected_tool']} selected={miss['selected_tool'] or '-'} "
            f"error={miss['error'] or '-'} :: {miss['message']}"
        )


def register_agent_commands(app):
    """Register agent CLI commands on the Flask app."""
    app.cli.add_command(agent_cli)
