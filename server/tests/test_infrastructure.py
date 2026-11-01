from pathlib import Path


def test_container_app_uses_secure_direct_secret_during_initial_deployment():
    source = (
        Path(__file__).resolve().parents[2] / "infra" / "modules" / "resources.bicep"
    ).read_text(encoding="utf-8")

    assert "name: 'api-bearer-token'\n        value: apiBearerToken" in source
    assert "keyVaultUrl:" not in source


def test_container_apps_environment_enables_public_network_for_mobile_api():
    source = (
        Path(__file__).resolve().parents[2] / "infra" / "modules" / "resources.bicep"
    ).read_text(encoding="utf-8")
    environment_module = source.split("module containerEnvironment", 1)[1].split(
        "module api",
        1,
    )[0]

    assert "publicNetworkAccess: 'Enabled'" in environment_module


def test_mobile_demo_access_code_is_injected_as_container_secret():
    source = (
        Path(__file__).resolve().parents[2] / "infra" / "modules" / "resources.bicep"
    ).read_text(encoding="utf-8")

    assert "name: 'demo-access-code'\n        value: demoAccessCode" in source
    assert (
        "name: 'DEMO_ACCESS_CODE'\n            secretRef: 'demo-access-code'"
        in source
    )
    assert "name: 'demo-session-secret'\n        value: demoSessionSecret" in source
    assert (
        "name: 'DEMO_SESSION_SECRET'\n            secretRef: 'demo-session-secret'"
        in source
    )
