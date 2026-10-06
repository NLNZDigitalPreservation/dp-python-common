import os
from argparse import ArgumentParser


def str2bool(value):
    true_values = {"true", "1", "yes", "y", "t", "on"}
    false_values = {"false", "0", "no", "n", "f", "off"}

    value = value.strip().lower()
    if value in true_values:
        return True
    elif value in false_values:
        return False
    else:
        raise ValueError(f"Invalid truth value: {value}")


def _to_env_var_name(flag_name: str) -> str:
    """Converts a flag to an idiomatic environment variable name"""
    return flag_name.replace("--", "").replace("-", "_").upper()


class Parser(ArgumentParser):
    """An easy way to make flags also configurable from env variables"""

    def add_env_argument(self, *args, **kwargs):
        if len(args) != 1:
            raise ValueError("Provide exactly one flag name")

        flag_name = args[0]

        # Prioritize environment variables over the normal default
        environment_default = os.environ.get(_to_env_var_name(flag_name), None)
        if environment_default is not None:
            # If a type is specified such as 'int' or 'float' or 'str', convert
            # the environment variable using the callback
            type_callback = kwargs.get("type", None)
            if type_callback:
                environment_default = type_callback(environment_default)

            kwargs["default"] = environment_default

        # Mark the flag as not required if it's supplied as an env variable
        no_env_variable_set = _to_env_var_name(flag_name) not in os.environ
        marked_required = kwargs.get("required", False)
        kwargs["required"] = marked_required and no_env_variable_set

        super().add_argument(flag_name, **kwargs)
