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


def test_public_mobile_demo_has_no_access_code_secrets():
    root = Path(__file__).resolve().parents[2]
    resources = (root / "infra" / "modules" / "resources.bicep").read_text(
        encoding="utf-8"
    )
    main = (root / "infra" / "main.bicep").read_text(encoding="utf-8")
    parameters = (root / "infra" / "main.parameters.json").read_text(
        encoding="utf-8"
    )

    for source in (resources, main, parameters):
        assert "demoAccessCode" not in source
        assert "demoSessionSecret" not in source
        assert "DEMO_ACCESS_CODE" not in source
        assert "DEMO_SESSION_SECRET" not in source


def test_reviewed_manual_is_staged_in_image_and_configured_for_runtime():
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "server" / "Dockerfile").read_text(encoding="utf-8")
    bicep = (root / "infra" / "modules" / "resources.bicep").read_text(
        encoding="utf-8"
    )

    assert "COPY data ./data" not in dockerfile
    assert "python -m visual_guide.manual_staging" in dockerfile
    assert "WD80H25BHS_OID139796_KO.pdf" in dockerfile
    assert (
        "name: 'REVIEWED_MANUAL_PATH'\n"
        "            value: '/app/data/WD80H25BHS_OID139796_KO.pdf'"
    ) in bicep
