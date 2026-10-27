import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def hardened():
    return (ROOT / "tests/fixtures/hardened-deployment.yaml").read_text()


@pytest.fixture
def samples():
    return {p.name: p.read_text() for p in sorted((ROOT / "samples").glob("*.yaml"))}
