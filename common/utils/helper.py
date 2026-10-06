import os

import falcon


def is_empty_str(param):
    return param is None or len(param.strip()) == 0


def assert_empty(key, data_json):
    if data_json is None:
        raise falcon.HTTPBadRequest(
            title="Bad request", description="The input request body is null."
        )

    if key in data_json and data_json[key] is not None:
        raise falcon.HTTPBadRequest(
            title="Bad request", description=f"The {key} should be null."
        )


def assert_not_empty(key, data_json):
    if data_json is None:
        raise falcon.HTTPBadRequest(
            title="Bad request", description="The input request body is null."
        )

    if key not in data_json or data_json[key] is None:
        raise falcon.HTTPBadRequest(
            title="Bad request", description=f"The {key} can not be null."
        )


def format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f}{unit}"
        size /= 1024


def format_rate(total_bytes: int, elapsed_seconds: float) -> str:
    if elapsed_seconds <= 0:
        return "N/A"
    return f"{format_bytes(total_bytes / elapsed_seconds)}/s"


def running_in_container():
    # Docker
    if os.path.exists("/.dockerenv"):
        return True
    # Podman
    if os.path.exists("/run/.containerenv"):
        return True
    # Check cgroups for hints
    try:
        with open("/proc/1/cgroup", "rt") as f:
            for line in f:
                if any(x in line for x in ("docker", "kubepods", "podman", "libpod")):
                    return True
    except FileNotFoundError:
        pass
    return False
