"""Typer CLI for FlowGate."""

from __future__ import annotations

import base64
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from flowgate import __version__

app = typer.Typer(
    name="flow-router",
    help="FlowGate - Local-first LLM gateway with cost audit dashboard",
    add_completion=False,
)
console = Console()


@app.command()
def start(
    host: str = typer.Option("127.0.0.1", help="Bind host address"),
    port: int = typer.Option(7798, help="Bind port"),
    config: Optional[str] = typer.Option(None, help="Path to flowgate.yaml config file"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
):
    """Start the FlowGate local gateway."""
    import os

    import uvicorn

    from flowgate.config import load_settings

    settings = load_settings(config)
    actual_host = host or settings.server.host
    actual_port = port or settings.server.port

    if settings.security.vault_enabled and not os.environ.get("FLOWGATE_MASTER_PASSWORD"):
        _prompt_master_password(settings)

    console.print(
        Panel.fit(
            f"[bold cyan]FlowGate[/bold cyan] v{__version__}\n\n"
            f"  Dashboard:  [green]http://{actual_host}:{actual_port}[/green]\n"
            f"  API Proxy:  [green]http://{actual_host}:{actual_port}/v1[/green]\n"
            f"  API Docs:   [green]http://{actual_host}:{actual_port}/docs[/green]\n\n"
            f"  Database:   [dim]{settings.database.path}[/dim]\n"
            f"  IP Mode:    [dim]{settings.security.ip_whitelist.mode}[/dim]\n"
            f"  Vault:      [dim]{'enabled' if settings.security.vault_enabled else 'disabled'}[/dim]",
            border_style="cyan",
        )
    )

    if config:
        os.environ["FLOWGATE_CONFIG"] = config
    os.environ["FLOWGATE_HOST"] = actual_host
    os.environ["FLOWGATE_PORT"] = str(actual_port)

    uvicorn.run(
        "flowgate.app:create_app",
        host=actual_host,
        port=actual_port,
        reload=reload,
        log_level=settings.logging.level.lower(),
        factory=True,
    )


@app.command(name="add-key")
def add_key(
    config: Optional[str] = typer.Option(None, help="Path to flowgate.yaml config file"),
):
    """Interactively add a provider API key to the encrypted vault."""
    from flowgate.config import load_settings
    from flowgate.db.engine import get_session, init_db
    from flowgate.db.models import ProviderKey, VaultMeta
    from flowgate.security.vault import Vault

    settings = load_settings(config)
    init_db(settings.database.path)

    vault = Vault()
    db_path = settings.database.path
    session = get_session(db_path)

    try:
        meta = session.get(VaultMeta, 1)
        if meta is None:
            console.print("[yellow]Vault not initialized. Setting up master password first...[/yellow]")
            password = Prompt.ask("[bold]Set master password", password=True)
            confirm = Prompt.ask("[bold]Confirm master password", password=True)
            if password != confirm:
                console.print("[red]Passwords do not match.[/red]")
                raise typer.Exit(1)
            salt = vault.initialize(password)
            meta = VaultMeta(
                id=1,
                salt=base64.b64encode(salt).decode(),
                password_hash=Vault.hash_password(password),
            )
            session.add(meta)
            session.commit()
            console.print("[green]Master password set successfully.[/green]")
        else:
            password = Prompt.ask("[bold]Enter master password", password=True)
            if Vault.hash_password(password) != meta.password_hash:
                console.print("[red]Invalid master password.[/red]")
                raise typer.Exit(1)
            salt = base64.b64decode(meta.salt)
            vault.initialize(password, salt=salt)
    finally:
        session.close()

    provider = Prompt.ask(
        "[bold]Provider[/bold]",
        choices=["openai", "anthropic", "google", "azure", "deepseek", "qwen", "other"],
    )
    if provider == "other":
        provider = Prompt.ask("[bold]Custom provider name[/bold]")

    key_name = Prompt.ask("[bold]Key name[/bold] (e.g. 'Production')", default=f"{provider}-default")
    api_key = Prompt.ask("[bold]API Key[/bold]", password=True)

    if not api_key:
        console.print("[red]API key cannot be empty.[/red]")
        raise typer.Exit(1)

    encrypted = vault.encrypt_key(api_key)
    suffix = api_key[-4:] if len(api_key) >= 4 else api_key

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    pk = ProviderKey(
        provider=provider,
        key_name=key_name,
        encrypted_key=encrypted,
        key_suffix=suffix,
        enabled=True,
        created_at=now,
        updated_at=now,
    )

    session = get_session(db_path)
    try:
        session.add(pk)
        session.commit()
    finally:
        session.close()

    masked = Vault.mask_key(api_key)
    console.print(f"\n[green]Key added:[/green] {provider} / {key_name} ({masked})")


@app.command()
def version():
    """Show FlowGate version."""
    console.print(f"FlowGate v{__version__}")


def _prompt_master_password(settings) -> None:
    """At startup, prompt for master password and set env var for auto-unlock."""
    import os

    from flowgate.db.engine import get_session, init_db
    from flowgate.db.models import VaultMeta
    from flowgate.security.vault import Vault

    init_db(settings.database.path)
    session = get_session(settings.database.path)
    try:
        meta = session.get(VaultMeta, 1)
    finally:
        session.close()

    if meta is None:
        console.print("[yellow]No vault found. You can set it up via the dashboard or `flow-router add-key`.[/yellow]")
        return

    password = Prompt.ask("[bold cyan]Enter master password to unlock vault[/bold cyan]", password=True)
    if Vault.hash_password(password) != meta.password_hash:
        console.print("[red]Invalid master password. Vault will remain locked.[/red]")
        return

    os.environ["FLOWGATE_MASTER_PASSWORD"] = password
    console.print("[green]Vault will be unlocked on startup.[/green]")


if __name__ == "__main__":
    app()
