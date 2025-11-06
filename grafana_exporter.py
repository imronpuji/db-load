from typing import Optional

from prometheus_client import start_http_server


def start_prometheus_exporter(port: int) -> None:
    # Starts a background HTTP server on the given port
    start_http_server(port)


__all__ = ["start_prometheus_exporter"]


