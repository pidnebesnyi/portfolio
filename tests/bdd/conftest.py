"""Gherkin scenarios on top of the existing framework.

The .feature files (tests/bdd/features) say what the product does in business words; the step
modules (tests/bdd/steps) translate each sentence into calls on the clients, factories and page
objects the other layers already use. Each scenario is bound to one test function in a
test_*.py file next to this one, which carries the title, tier marker and requirement.

Allure: every Gherkin step becomes a step of the test result, named as written in the feature.
"""

import allure
import pytest
from pytest_bdd.parser import Feature, Scenario, Step

# pytest-bdd registers a step as a fixture in the module that defines it, and pytest_plugins is not
# allowed in this conftest, so the step modules are star-imported: that makes the steps of every
# feature visible to every scenario in this folder.
from tests.bdd.steps.access import *  # noqa: F403
from tests.bdd.steps.common import *  # noqa: F403
from tests.bdd.steps.idempotency import *  # noqa: F403
from tests.bdd.steps.provider import *  # noqa: F403
from tests.bdd.steps.refunds import *  # noqa: F403
from tests.bdd.steps.ui_refund import *  # noqa: F403

# Fixtures owned by other layers, reused as they are: the browser session from tests/ui and the
# provider stub from tests/integration. Importing them here makes them visible to this folder only.
from tests.integration.conftest import provider_stub  # noqa: F401
from tests.ui.conftest import (  # noqa: F401
    _expect_timeout,
    base_url,
    browser_context_args,
    delete_output_dir,
    merchant_page,
)

OPEN_STEPS = pytest.StashKey[list]()


def pytest_bdd_before_step(
    request: pytest.FixtureRequest,
    feature: Feature,
    scenario: Scenario,
    step: Step,
    step_func: object,
) -> None:
    context = allure.step(f"{step.keyword} {step.name}")
    context.__enter__()
    request.node.stash.setdefault(OPEN_STEPS, []).append(context)


def pytest_bdd_after_step(
    request: pytest.FixtureRequest,
    feature: Feature,
    scenario: Scenario,
    step: Step,
    step_func: object,
    step_func_args: dict,
) -> None:
    request.node.stash[OPEN_STEPS].pop().__exit__(None, None, None)


def pytest_bdd_step_error(
    request: pytest.FixtureRequest,
    feature: Feature,
    scenario: Scenario,
    step: Step,
    step_func: object,
    step_func_args: dict,
    exception: Exception,
) -> None:
    request.node.stash[OPEN_STEPS].pop().__exit__(
        type(exception), exception, exception.__traceback__
    )
    # Shown under the assertion in the pytest output, so the failure names the sentence that broke.
    exception.add_note(
        f"Failed step: {step.keyword} {step.name} ({feature.rel_filename}:{step.line_number})"
    )
