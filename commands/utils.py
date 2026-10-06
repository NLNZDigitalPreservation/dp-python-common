import argparse
import getpass
import grp
import json
import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import set_key

DEFAULT_INSTALL_PATH = "/data/viridian/conf"
DEFAULT_DATA_PATH = "/data/viridian/persistent"

INSTALL_PATH_KEY = "install_path"
DATA_PATH_KEY = "data_path"

DEFAULT_CONFIG_SUBDIR = "viridian"
DEFAULT_CONFIG_FILE = "config.json"


def run(command: List[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"Running: {' '.join(command)}")
    return subprocess.run(command, text=True, check=check)


def select_engine(engine: str) -> str:
    if engine in ("podman", "docker"):
        return engine
    if shutil.which("podman"):
        return "podman"
    if shutil.which("docker"):
        return "docker"
    raise RuntimeError("Neither podman nor docker is installed.")


def select_compose_command(engine: str) -> List[str]:
    if engine == "podman":
        if shutil.which("podman-compose"):
            return ["podman-compose"]
        return ["podman", "compose"]
    if engine == "docker":
        return ["docker", "compose"]
    raise RuntimeError(f"Unsupported container engine: {engine}")


def resource_file(app_name: str, *parts: str):
    """Return a Traversable for a path inside viridian.resources/<app_name>."""
    resource = resources.files("viridian.resources").joinpath(app_name)
    for part in parts:
        resource = resource.joinpath(part)
    return resource


def config_dir() -> Path:
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        return Path(xdg_home).expanduser() / DEFAULT_CONFIG_SUBDIR
    return Path.home() / ".config" / DEFAULT_CONFIG_SUBDIR


def _config_file() -> Path:
    return config_dir() / DEFAULT_CONFIG_FILE


def load_config() -> Dict[str, str]:
    path = _config_file()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def save_config(config: Dict[str, str]) -> None:
    cfg_dir = config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    with _config_file().open("w", encoding="utf-8") as fp:
        json.dump(config, fp, indent=2, sort_keys=True)
        fp.write("\n")


def persist_path(app_name: str, path_key: str, path: Path | str) -> None:
    cfg = load_config()
    if app_name not in cfg:
        cfg[app_name] = {}

    cfg[app_name][path_key] = str(path)
    save_config(cfg)


def run_installed_compose(
    engine: str,
    install_path: Path,
    project_name: str,
    extra: List[str],
) -> None:
    compose_file = install_path / "docker-compose.yml"
    if not compose_file.exists():
        raise FileNotFoundError(
            f"{compose_file} not found. Run '{project_name} install' first."
        )
    compose_cmd = select_compose_command(engine)
    cmd = compose_cmd + ["-p", project_name, "-f", str(compose_file)]
    env_file = install_path / ".env"
    if env_file.exists():
        cmd += ["--env-file", str(env_file)]
    cmd += extra
    run(cmd)


def path_state(path: Path) -> str:
    return "exists" if path.exists() else "missing"


def prompt(message: str, default: str) -> str:
    try:
        answer = input(f"{message} [{default}]: ").strip()
    except EOFError:
        answer = ""
    return answer if answer else default


def create_network(engine: str, network_name: str = "viridian-network") -> None:
    runtime = shutil.which(engine)
    if runtime is None:
        raise RuntimeError(f"{engine} not found.")

    result = subprocess.run(
        [runtime, "network", "inspect", network_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode != 0:
        subprocess.run(
            [runtime, "network", "create", network_name],
            check=True,
        )

    print(f"Using network: {network_name}")


def install_packaged_assets(install_path: Path, app_name: str) -> None:
    """Copy every file and sub-directory from the app's resources folder to *install_path*."""
    app_resources = resource_file(app_name)

    if not app_resources.is_dir():
        raise FileNotFoundError(
            f"Bundled resource directory missing: resources/{app_name}/. "
            "Rebuild/reinstall viridian-cli."
        )

    with resources.as_file(app_resources) as src_dir:
        for entry in src_dir.iterdir():
            dst = install_path / entry.name
            if entry.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(entry, dst)
            else:
                shutil.copy2(entry, dst)
            print(f"  Installed: {dst}")


def resolve_path(app_name: str, default_path: str, prompt_desc: str) -> Path:
    # Determine install directory.
    resolved_default = Path(default_path, app_name)
    resolved_default = resolved_default.expanduser().resolve()

    chosen = prompt(prompt_desc, resolved_default)
    resolved_path = Path(chosen).expanduser().resolve()

    # Create directory if needed.
    if app_name == "oracle":
        username = "54321"
        group_name = "54321"
    else:
        username = getpass.getuser()
        group_name = grp.getgrgid(os.getgid()).gr_name

    if not resolved_path.exists():
        print(f"  Creating {resolved_path} ...")
        run(["mkdir", "-p", str(resolved_path)])
        run(["chown", f"{username}:{group_name}", str(resolved_path)])
        if app_name == "oracle":
            run(["chmod", "777", str(resolved_path)])
        print(f"  Created: {resolved_path}")
    else:
        print(f"  Using existing: {resolved_path}")

    return resolved_path


def print_no_braces(obj, indent=2, is_list_item=False):
    """
    Recursively print a JSON-like object without displaying curly braces ({})
    or square brackets ([]). Hierarchy is represented using indentation and
    line breaks.

    Args:
        obj: The Python object to print (dict or list).
        indent: The current indentation level (number of spaces).
        is_list_item: Whether the current object is a list item. If True,
            the first key of a dictionary is prefixed with "- ".
    """
    space = " " * indent

    if isinstance(obj, dict):
        for key, value in obj.items():
            # Determine the prefix for the current line.
            # The first key of a dictionary inside a list is prefixed with "- ".
            if is_list_item:
                line_prefix = f"{space}- {key}"
                is_list_item = False  # Only prefix the first key with "- ".
            else:
                line_prefix = f"{space}{key}"

            if isinstance(value, dict):
                print(f"{line_prefix}:")
                print_no_braces(value, indent + 2, False)

            elif isinstance(value, list):
                print(f"{line_prefix}:")
                for item in value:
                    if isinstance(item, dict):
                        # Recursively print dictionary items in the list.
                        print_no_braces(item, indent + 2, True)
                    else:
                        # Print primitive values in the list.
                        print(f"{space}  - {item}")

            else:
                print(f"{line_prefix}: {value}")

    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                print_no_braces(item, indent, True)
            else:
                print(f"{space}- {item}")
    # print(yaml.safe_dump(obj, sort_keys=False))


def cmd_info(app_name: Optional[str] = None) -> None:
    cfg = load_config()

    if cfg is None or len(cfg) == 0:
        print("No installation information found. Run 'install' first.")
        return

    if app_name is None:
        print("Installation information:")
        print_no_braces(cfg)
        return

    app_cfg = cfg.get(app_name)
    if app_cfg is None or len(app_cfg) == 0:
        print(
            f"No installation information found for {app_name}. Run '{app_name} install' first."
        )
        return

    print(f"Installation information for {app_name}:")
    print_no_braces(app_cfg)


def cmd_install(app_name: str) -> None:
    app_version = prompt(f"Please choose a version for {app_name}", "latest")

    # Initialize installation directory.
    install_path = resolve_path(
        app_name, DEFAULT_INSTALL_PATH, "Installation directory"
    )
    # Copy bundled compose resources files.
    install_packaged_assets(install_path, app_name)

    # Initialize persistent data directory.
    data_path = resolve_path(app_name, DEFAULT_DATA_PATH, "Persistent storage root")

    persist_path(app_name, "version", app_version)
    persist_path(app_name, INSTALL_PATH_KEY, install_path)
    persist_path(app_name, DATA_PATH_KEY, data_path)

    print(f"Saved config: {_config_file()}")

    env_template = install_path / "template.env"
    env_file = install_path / ".env"

    if not env_template.exists():
        env_file.write_text("")
    else:
        shutil.copy2(env_template, env_file)

    set_key(
        str(env_file), f"{app_name.upper()}_VERSION", app_version, quote_mode="never"
    )
    set_key(str(env_file), "SOURCE_INSTALL_PATH", str(install_path), quote_mode="never")
    set_key(str(env_file), "SOURCE_PERSISTENT_PATH", str(data_path), quote_mode="never")
    print(f"Updated .env: {env_file}")

    return install_path, data_path


def cmd_container(args: argparse.Namespace, app_name, engine: str) -> None:
    cfg = load_config()
    if cfg is None or app_name not in cfg:
        app_cfg = {}
    else:
        app_cfg = cfg[app_name]
    install_path_str = app_cfg.get(
        INSTALL_PATH_KEY, Path(DEFAULT_INSTALL_PATH, app_name).expanduser().resolve()
    )
    install_path = Path(install_path_str).expanduser().resolve()

    if args.command == "up":
        run_installed_compose(engine, install_path, app_name, ["up", "--detach"])
        return
    if args.command == "down":
        run_installed_compose(engine, install_path, app_name, ["down"])
        return
    if args.command == "restart":
        run_installed_compose(engine, install_path, app_name, ["restart"])
        return
    if args.command == "status":
        run_installed_compose(engine, install_path, app_name, ["ps"])
        return
    if args.command == "logs":
        compose_args = ["logs"]
        if not args.no_follow:
            compose_args.append("-f")
        run_installed_compose(engine, install_path, app_name, compose_args)
        return
    if args.command == "exec":
        run([engine, "exec", "-it", app_name, args.shell])
        return
    raise RuntimeError(f"Unsupported {app_name} command: {args.command}")
