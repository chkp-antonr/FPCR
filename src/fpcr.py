import asyncio
import os
from pathlib import Path

import typer
from arlogi import get_logger, setup_logging
from cpaiops import CPAIOPSClient
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from sqlalchemy.ext.asyncio import create_async_engine

from cpcrud import apply_crud_templates
from cpsearch import DomainSearchResult, GroupNode, find_cp_objects
from utils import log_elapsed_time

# Load environment variables
load_dotenv(".env")
load_dotenv(".env.secrets")


def init_logging() -> None:
    """Initialize logging configuration based on environment variables."""
    # The .env should have LOG_LEVEL=TRACE or DEBUG
    log_level = os.getenv("LOG_LEVEL", "INFO")
    cpaiops_log_level = os.getenv("CPAIOPS_LOG_LEVEL", "INFO")

    setup_logging(
        level=log_level,
        module_levels={
            "cpaiops": cpaiops_log_level,
            "sqlalchemy": "WARNING",
            "sqlalchemy.engine": "WARNING",
            "sqlalchemy.pool": "WARNING",
            "aiosqlite": "WARNING",
            "httpcore": "WARNING",
            "httpx": "WARNING",
            "aiohttp": "WARNING",
            "asyncio": "WARNING",
        },
    )


# Initialize logging
init_logging()
logger = get_logger(__name__)

app = typer.Typer(
    help="Check Point Firewall Policy Change Request Tool",
    no_args_is_help=True,
)
console = Console()


def get_client() -> CPAIOPSClient:
    """Initialize and return a CPAIOPSClient instance."""
    mgmt_ip = os.getenv("API_MGMT")
    username = os.getenv("API_USERNAME")
    password = os.getenv("API_PASSWORD")
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///sessions.db")

    if not all([mgmt_ip, username, password]):
        console.print(
            "[red]Error: API_MGMT, API_USERNAME, and API_PASSWORD must be set in environment.[/red]"
        )
        raise typer.Exit(code=1)

    engine = create_async_engine(db_url)
    return CPAIOPSClient(
        engine=engine,
        username=username,
        password=password,
        mgmt_ip=mgmt_ip,
    )


@app.command()
def show_domains() -> None:
    """Show domains and display their names."""

    async def _run() -> None:
        # logger.debug("Starting show-domains command (DEBUG test)")
        # logger.trace("Testing TRACE level logging")

        client = get_client()
        console.print(
            f"Connecting to management server at [cyan]{client.settings.mgmt_ip}[/cyan]..."
        )

        try:
            async with client:
                server_names = client.get_mgmt_names()
                if not server_names:
                    console.print("[yellow]No management servers registered.[/yellow]")
                    return

                mgmt_name = server_names[0]
                # logger.debug(f"Resolved mgmt_name: {mgmt_name}")

                console.print(f"Retrieving domains from [green]{mgmt_name}[/green]...")
                result = await client.api_query(mgmt_name, "show-domains")

                if result.success:
                    if not result.objects:
                        console.print("[yellow]No domains found.[/yellow]")
                        return

                    table = Table(title="\nAvailable Domains")
                    table.add_column("Index", style="dim", width=6)
                    table.add_column("Name", style="magenta")
                    table.add_column("UID", style="dim")

                    for i, obj in enumerate(result.objects, 1):
                        name = obj.get("name", "Unknown")
                        uid = obj.get("uid", "N/A")
                        table.add_row(str(i), name, uid)

                    console.print(table)
                    logger.info(f"Successfully displayed {len(result.objects)} domains")
                else:
                    console.print(f"[red]Failed to query domains: {result.message}[/red]")
                    logger.error(f"API query failed: {result.message} (Code: {result.code})")

        except Exception as e:
            logger.exception(f"Unexpected error in show_domains: {e}")
            console.print(f"[bold red]Error:[/bold red] {e}")
        finally:
            logger.trace("CPAIOPSClient closed")

    asyncio.run(_run())


@app.command()
def cpcrud(
    template_files: list[Path] = typer.Argument(..., help="YAML template files to process"),
    no_publish: bool = typer.Option(False, "--no-publish", help="Do not publish changes"),
) -> None:
    """Process Check Point CRUD templates (YAML)."""

    async def _run() -> None:
        client = get_client()
        async with client:
            files = [str(f) for f in template_files]
            await apply_crud_templates(client, files, no_publish=no_publish)

    asyncio.run(_run())


@app.command()
def search_object(
    search: str = typer.Argument(..., help="IP, CIDR, IP range, or object name to search for"),
    max_depth: int = typer.Option(3, "--max-depth", "-d", help="Max group nesting depth"),
) -> None:
    """Search for Check Point objects across all domains and show group memberships."""

    def _build_group_tree(parent: Tree, nodes: list[GroupNode]) -> None:
        """Recursively add GroupNode children to a rich Tree."""
        for node in nodes:
            branch = parent.add(f"[cyan]{node.name}[/cyan]  [dim](depth {node.depth})[/dim]")
            if node.children:
                _build_group_tree(branch, node.children)

    def _render_results(results: dict[str, DomainSearchResult]) -> None:
        """Pretty-print search results using Rich tables and trees."""
        if not results:
            console.print("[yellow]No objects found.[/yellow]")
            return

        # --- Objects table ---
        table = Table(title="\n[bold]Found Objects[/bold]")
        table.add_column("Domain", style="magenta")
        table.add_column("Name", style="green")
        table.add_column("Type", style="cyan")
        table.add_column("Address / Range")
        table.add_column("Origin", style="yellow")
        table.add_column("UID", style="dim")

        for domain_result in results.values():
            for obj in domain_result.objects:
                origin = obj.orig_domain if obj.is_global else ""
                table.add_row(
                    obj.domain,
                    obj.name,
                    obj.obj_type,
                    obj.address_display,
                    origin,
                    obj.uid,
                )

        console.print(table)

        # --- Membership trees ---
        has_memberships = any(r.memberships for r in results.values())
        if has_memberships:
            console.print("\n[bold]Group Memberships[/bold]")
            for domain_result in results.values():
                for obj in domain_result.objects:
                    group_nodes = domain_result.memberships.get(obj.uid, [])
                    if not group_nodes:
                        continue
                    root = Tree(f"[bold green]{obj.name}[/bold green]  [dim]({obj.domain})[/dim]")
                    _build_group_tree(root, group_nodes)
                    console.print(root)

        # --- Errors ---
        errors = [r for r in results.values() if r.error]
        if errors:
            console.print()
            for r in errors:
                console.print(f"[red]⚠  {r.domain_name}: {r.error}[/red]")

    async def _run() -> None:
        client = get_client()
        console.print(
            f"Searching for [cyan]{search}[/cyan] on "
            f"[cyan]{client.settings.mgmt_ip}[/cyan] "
            f"(max depth {max_depth})..."
        )

        try:
            async with client:
                results = await find_cp_objects(client, search, max_depth=max_depth)
                _render_results(results)
        except Exception as e:
            logger.exception(f"Search failed: {e}")
            console.print(f"[bold red]Error:[/bold red] {e}")

    asyncio.run(_run())


@app.command()
def test_logs() -> None:
    """Demonstrate different logging levels."""
    logger.trace("This is a TRACE message")
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")
    console.print("[green]Check the console for colored log output at different levels.[/green]")


@log_elapsed_time
def _main() -> None:
    """Main entry point with timing measurement."""
    app()


if __name__ == "__main__":
    _main()
