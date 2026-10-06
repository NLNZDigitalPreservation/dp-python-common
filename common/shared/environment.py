import faulthandler
import logging
import os


def set_up_environment():
    """This function reduces duplicate code across microservices by setting up
    logging based on an environment variable 'LOGLEVEL' and by enabling the
    python faulthandler.
    """

    # Set the log level
    default_log_level = "INFO"
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=os.environ.get("LOGLEVEL", default_log_level),
    )

    # Enable faulthandler
    faulthandler.enable()

    return os.environ.get("OPTIONAL_DB_TABLES", "enabled")
