"""The OpenAPI document the service publishes, compared with the one pinned in the repository.

Every response the suite receives is already checked against the live document (the `http`
client, tests/utils/openapi.py). That alone would let the document and the code drift together:
rename a field in both and every test stays green while every integrator breaks. Pinning the
document closes that gap. A change to the API is only accepted together with a change to
tests/contract/openapi.json, so it shows up in the pull request diff and someone reviews it.
"""

import json
from pathlib import Path
from typing import Any

import allure
import pytest

from tests.utils.allure_links import area, requirement
from tests.utils.openapi import spec_diff

PINNED = Path(__file__).with_name("openapi.json")

pytestmark = [pytest.mark.smoke, area("API contract"), requirement("API-CONTRACT")]


@allure.title("The published OpenAPI document matches the pinned contract")
def test_published_document_matches_the_pinned_contract(openapi_spec: dict[str, Any]) -> None:
    pinned = json.loads(PINNED.read_text(encoding="utf-8"))
    changes = spec_diff(pinned, openapi_spec)
    if changes:
        allure.attach("\n".join(changes), name="OpenAPI changes", attachment_type="text/plain")
    assert not changes, (
        "the service's OpenAPI document differs from tests/contract/openapi.json:\n"
        + "\n".join(changes)
        + "\nIf the change is intended, run scripts/export_openapi.py against the running "
        "service and commit the file with the change."
    )
