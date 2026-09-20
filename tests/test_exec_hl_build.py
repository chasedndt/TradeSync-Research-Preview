"""exec-hl-svc builds from the repository root and installs tradesync_core, as signer-svc does.

The order route's caller token and the signer client both come from
``tradesync_core.service_tokens``. The image used to be built from the service
directory alone, where the library does not exist, so an import that passed
every test (the test runner puts the library on the path) would have failed in
the container.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _instructions(service: str) -> list[str]:
    lines = (ROOT / "services" / service / "Dockerfile").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def test_the_image_installs_the_shared_library_and_only_the_service_code() -> None:
    steps = _instructions("exec-hl-svc")
    assert "COPY libs/tradesync_core /tmp/tradesync_core" in steps
    assert "RUN pip install --no-cache-dir /tmp/tradesync_core && rm -rf /tmp/tradesync_core" in steps
    assert "COPY services/exec-hl-svc/app /app/app" in steps
    assert "COPY . ." not in steps
    assert steps[-1] == 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]'


def test_compose_builds_it_from_the_repository_root() -> None:
    full = yaml.safe_load((ROOT / "ops" / "compose.full.yml").read_text(encoding="utf-8"))
    build = full["services"]["exec-hl-svc"]["build"]
    assert build == {"context": "..", "dockerfile": "services/exec-hl-svc/Dockerfile"}
    # The same shape as the signer, which already installs the library this way.
    signer = yaml.safe_load((ROOT / "ops" / "compose.signer.yml").read_text(encoding="utf-8"))
    assert signer["services"]["signer-svc"]["build"]["context"] == ".."
