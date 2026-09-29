"""Root-equivalent component. No arbitrary Docker API passthrough is provided."""

import os
import threading

import docker
from docker.errors import NotFound
from fastapi import FastAPI, HTTPException
from nexus.protocol import validate_manifest
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
lock = threading.Lock()
INSTALLATION = os.getenv("NEXUS_INSTALLATION", "nexus")
LABEL = "org.aureate-empyrean.nexus"


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", max_length=48)
    manifest: dict | None = None
    resolver_key: str | None = Field(default=None, min_length=32, max_length=200)
    token: str | None = Field(default=None, min_length=32, max_length=200)


def owned(resource):
    if (
        resource.attrs.get("Labels", resource.attrs.get("Config", {}).get("Labels", {})).get(LABEL)
        != INSTALLATION
    ):
        raise ValueError("Refusing to modify a resource owned by another installation")
    return resource


def operate(action, body):
    client = docker.from_env(timeout=90)
    name = f"{INSTALLATION}-module-{body.id}"
    network_name = f"{INSTALLATION}-net-{body.id}"
    if action == "status":
        try:
            container = owned(client.containers.get(name))
            network = owned(client.networks.get(network_name))
            for gateway in client.containers.list(
                filters={"label": f"{LABEL}.gateway={INSTALLATION}"}
            ):
                if network_name not in gateway.attrs["NetworkSettings"]["Networks"]:
                    network.connect(gateway, aliases=["nexus"])
            return {"state": container.status}
        except NotFound:
            return {"state": "absent"}
    if action == "enable":
        manifest = validate_manifest(body.manifest, os.getenv("NEXUS_ALLOW_EXAMPLE") == "1")
        if manifest["id"] != body.id or not body.token:
            raise ValueError("Manifest identity and token are required")
        gateways = client.containers.list(filters={"label": f"{LABEL}.gateway={INSTALLATION}"})
        if len(gateways) != 1:
            raise ValueError("Expected exactly one running Nexus gateway")
        try:
            container = owned(client.containers.get(name))
            container.remove(force=True)
        except NotFound:
            pass
        try:
            network = owned(client.networks.get(network_name))
        except NotFound:
            network = client.networks.create(
                network_name, driver="bridge", internal=True, labels={LABEL: INSTALLATION}
            )
        gateway = gateways[0]
        if network_name not in gateway.attrs["NetworkSettings"]["Networks"]:
            network.connect(gateway, aliases=["nexus"])
        image = manifest["container"]["image"]
        if "@sha256:" in image:
            resolved = client.images.pull(image)
        else:
            resolved = client.images.get(image)  # Local reference exception; never pull a tag.
        if resolved.attrs.get("Config", {}).get("Volumes"):
            raise ValueError("Image-declared volumes are not supported in protocol v1")
        container = client.containers.run(
            resolved.id,
            detach=True,
            name=name,
            hostname=f"module-{body.id}",
            network=network_name,
            networking_config={
                network_name: client.api.create_endpoint_config(aliases=[f"module-{body.id}"])
            },
            labels={LABEL: INSTALLATION},
            user="10001:10001",
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            pids_limit=64,
            mem_limit="256m",
            nano_cpus=500_000_000,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16777216,uid=10001,gid=10001"},
            environment={
                **({"NEXUS_RESOLVER_KEY": body.resolver_key} if body.resolver_key else {}),
                "NEXUS_URL": "http://nexus:12333",
                "NEXUS_MODULE_ID": body.id,
                "NEXUS_TOKEN": body.token,
                "MODULE_PORT": str(manifest["container"]["port"]),
            },
            restart_policy={"Name": "unless-stopped"},
            log_config=docker.types.LogConfig(
                type="json-file", config={"max-size": "5m", "max-file": "2"}
            ),
        )
        return {"state": "running"}
    if action not in {"disable", "uninstall"}:
        raise ValueError("Unsupported lifecycle operation")
    try:
        container = owned(client.containers.get(name))
        container.stop(timeout=10)
        container.remove()
    except NotFound:
        pass
    try:
        network = owned(client.networks.get(network_name))
        for gateway in client.containers.list(filters={"label": f"{LABEL}.gateway={INSTALLATION}"}):
            if network_name in gateway.attrs["NetworkSettings"]["Networks"]:
                network.disconnect(gateway)
        network.remove()
    except NotFound:
        pass
    return {"state": "absent"}


@app.post("/v1/{action}")
def operation(action: str, body: Operation):
    with lock:
        try:
            return operate(action, body)
        except (ValueError, docker.errors.DockerException) as exc:
            # Docker errors may contain environment details; do not return them to callers.
            print(f"Broker {action} failed for {body.id}: {type(exc).__name__}", flush=True)
            raise HTTPException(502, "Controlled runtime operation failed") from exc
