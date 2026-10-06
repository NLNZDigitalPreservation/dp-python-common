import argparse
from importlib import metadata

from viridian import __version__ as _viridian_version


def _get_version() -> str:
    """Return the package version, falling back to the module constant."""
    try:
        return metadata.version("viridian-cli")
    except metadata.PackageNotFoundError:
        return _viridian_version


def parse_args_app(app_name: str = "") -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=app_name, description=f"Viridian {app_name} helper"
    )
    parser.add_argument("--app-name", default=app_name, help="Name of the application")

    parser.add_argument(
        "--container-engine",
        choices=["auto", "podman", "docker"],
        default="auto",
        help="Container engine to use",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("up", "down", "restart", "status", "exec"):
        subparsers.add_parser(name, help=f"{name} {app_name} services")

    logs_cmd = subparsers.add_parser("logs", help=f"Follow {app_name} logs")
    logs_cmd.add_argument(
        "--no-follow", action="store_true", help="Do not follow log output"
    )

    # ── install / info ────────────────────────────────────────────────────────
    subparsers.add_parser(
        "install", help="Install compose files, db scripts, and .env templates"
    )

    subparsers.add_parser(
        "info", help="Show resolved installation path and persistent directory status"
    )

    parser.add_argument("--shell", default="bash", help="Shell to use for exec command")

    return parser.parse_args()
