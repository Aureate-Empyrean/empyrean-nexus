from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from broker.app import INSTALLATION, LABEL, Operation, operate
from docker.errors import NotFound


@pytest.fixture
def engine(monkeypatch):
    client = MagicMock()
    gateway = MagicMock()
    gateway.attrs = {"NetworkSettings": {"Networks": {}}}
    client.containers.list.return_value = [gateway]
    client.containers.get.side_effect = NotFound("missing")
    client.networks.get.side_effect = NotFound("missing")
    image = SimpleNamespace(id="sha256:resolved", attrs={"Config": {}})
    client.images.get.return_value = image
    client.images.pull.return_value = image
    monkeypatch.setattr("broker.app.docker.from_env", lambda **kw: client)
    monkeypatch.setenv("NEXUS_ALLOW_EXAMPLE", "1")
    return client


def test_fixed_runtime_security_policy(engine, manifest):
    result = operate("enable", Operation(id=manifest["id"], manifest=manifest, token="x" * 40))
    assert result == {"state": "running"}
    args, opts = engine.containers.run.call_args
    assert args == ("sha256:resolved",)
    assert opts["read_only"] and opts["cap_drop"] == ["ALL"]
    assert opts["user"] == "10001:10001"
    assert opts["security_opt"] == ["no-new-privileges:true"]
    assert opts["pids_limit"] == 64 and opts["mem_limit"] == "256m"
    assert opts["nano_cpus"] == 500_000_000
    assert not any(k in opts for k in ["ports", "volumes", "privileged", "devices", "command"])
    assert set(opts["environment"]) == {
        "NEXUS_URL",
        "NEXUS_TOKEN",
        "MODULE_PORT",
        "NEXUS_MODULE_ID",
    }
    assert engine.networks.create.call_args.kwargs["internal"] is True
    engine.images.pull.assert_not_called()


def test_no_implicit_image_volumes(engine, manifest):
    engine.images.get.return_value.attrs["Config"]["Volumes"] = {"/data": {}}
    with pytest.raises(ValueError, match="volumes"):
        operate("enable", Operation(id=manifest["id"], manifest=manifest, token="x" * 40))
    engine.containers.run.assert_not_called()


def test_broker_revalidates_privileged_manifest(engine, manifest):
    manifest["container"]["privileged"] = True
    with pytest.raises(ValueError):
        operate("enable", Operation(id=manifest["id"], manifest=manifest, token="x" * 40))
    engine.containers.run.assert_not_called()


def test_never_remove_foreign_container(engine):
    resource = MagicMock()
    resource.attrs = {"Config": {"Labels": {LABEL: "another-installation"}}}
    engine.containers.get.side_effect = None
    engine.containers.get.return_value = resource
    with pytest.raises(ValueError, match="another installation"):
        operate("uninstall", Operation(id="example"))
    resource.stop.assert_not_called()
    resource.remove.assert_not_called()


def test_cleanup_absent_resources_is_idempotent(engine):
    assert operate("uninstall", Operation(id="example")) == {"state": "absent"}


def test_status_reconnects_gateway_without_recreating_container(engine):
    container = MagicMock()
    container.attrs = {"Config": {"Labels": {LABEL: INSTALLATION}}}
    container.status = "running"
    engine.containers.get.side_effect = None
    engine.containers.get.return_value = container
    network = MagicMock()
    network.attrs = {"Labels": {LABEL: INSTALLATION}}
    engine.networks.get.side_effect = None
    engine.networks.get.return_value = network
    assert operate("status", Operation(id="example")) == {"state": "running"}
    network.connect.assert_called_once()
    assert network.connect.call_args.kwargs == {"aliases": ["nexus"]}
    engine.containers.run.assert_not_called()
