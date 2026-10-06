import shlex
import subprocess


def call_command(cmd_str: str):
    cmd_list = shlex.split(cmd_str)
    result = subprocess.run(cmd_list, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to process: {cmd_str}, error:{result.stderr}")

    return result.stdout
