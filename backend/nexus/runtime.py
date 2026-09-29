"""Nexus talks to a local Unix socket, never the Docker daemon."""

import httpx


class BrokerRuntime:
    def __init__(self, socket: str):
        self.socket = socket

    def call(self, action: str, module_id: str, manifest=None, token=None, resolver_key=None):
        try:
            with httpx.Client(
                transport=httpx.HTTPTransport(uds=self.socket),
                base_url="http://broker",
                timeout=120,
            ) as client:
                result = client.post(
                    f"/v1/{action}",
                    json={
                        "id": module_id,
                        "manifest": manifest,
                        "token": token,
                        "resolver_key": resolver_key,
                    },
                )
                result.raise_for_status()
                return result.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                "Lifecycle broker unavailable or operation rejected; inspect broker logs"
            ) from exc

    def target(self, module_id: str, port: int):
        return f"http://module-{module_id}:{port}"
