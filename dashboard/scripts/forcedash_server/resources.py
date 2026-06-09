"""Resource loading for remote Python programs."""
from importlib import resources

RESOURCE_PACKAGE = "forcedash_server.remote_scripts"


def read_remote_script(name: str) -> str:
    return resources.files(RESOURCE_PACKAGE).joinpath(name).read_text(encoding="utf-8")
