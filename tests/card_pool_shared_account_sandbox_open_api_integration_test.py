"""Sandbox shared-card flow backed by a selected card pool."""

from __future__ import annotations

import unittest
import uuid

from tests import share_card_sandbox_open_api_integration_test as shared_flow
from tests.share_card_sandbox_open_api_integration_test import (
    SandboxAccountsApiTest,
    SandboxAuthApiTest,
    SandboxCardGroupsApiTest,
    SandboxCardsApiTest,
    SandboxSharedAccountsApiTest,
    SandboxTransactionsApiTest,
)


class CardPoolSharedAccountSandboxOpenApiIntegrationTest(
    SandboxAuthApiTest,
    SandboxAccountsApiTest,
    SandboxTransactionsApiTest,
    SandboxSharedAccountsApiTest,
    SandboxCardsApiTest,
    SandboxCardGroupsApiTest,
):
    """Run the complete shared-card flow, including wallet and limit webhook shapes."""

    def test_list_card_pools_from_sandbox(self) -> None:
        selected_pool = self._selected_card_pool()
        self.assertIsNotNone(selected_pool)
        selected_bin = self._first_card_bin()
        self.assertIsNotNone(selected_bin)
        self.assertEqual(
            selected_pool.card_pool_id,
            selected_bin.card_pool_id,
            "Selected card BIN does not belong to the selected card pool",
        )

    def test_create_shared_account_from_sandbox(self) -> None:
        selected_pool = self._selected_card_pool()
        selected_bin = self._first_card_bin()
        self.assertEqual(
            selected_pool.card_pool_id,
            selected_bin.card_pool_id,
            "Shared-account card BIN must belong to the selected card pool",
        )
        self.assertIsNotNone(self._first_shared_account())

    def test_create_shared_account_with_card_bin_and_card_pool_from_sandbox(self) -> None:
        selected_pool = self._selected_card_pool()
        selected_bin = self._first_card_bin()
        self.assertEqual(
            selected_pool.card_pool_id,
            selected_bin.card_pool_id,
            "Shared-account card BIN must belong to the selected card pool",
        )
        created = self._authenticated_client().shared_accounts.create(
            shared_flow.CreateSharedAccountRequest(
                card_bin_id=selected_bin.card_bin_id,
                card_pool_id=selected_pool.card_pool_id,
                recharge_amount=self._shared_account_amount(),
                account_name=f"sdk-python-bin-pool-{uuid.uuid4().hex[:12]}",
            )
        )
        self.assertIsNotNone(created)
        self.assertTrue(created.member_shared_account_id)
        self._await_shared_account_open(created.member_shared_account_id)


def setUpModule() -> None:
    shared_flow.setUpModule()
    shared_flow.use_card_pool_flow()


def tearDownModule() -> None:
    shared_flow.tearDownModule()


_TEST_ORDER = (
    "test_get_token_from_sandbox",
    "test_refresh_token_from_sandbox",
    "test_logout_from_sandbox",
    "test_get_token_after_logout_from_sandbox",
    "test_list_card_pools_from_sandbox",
    "test_create_shared_account_from_sandbox",
    "test_create_shared_account_with_card_bin_and_card_pool_from_sandbox",
    "test_create_card_group_from_sandbox",
    "test_increase_shared_account_from_sandbox",
    "test_issue_card_from_sandbox",
    "test_wait_for_card_open_status_webhook_from_sandbox",
    "test_decrease_shared_account_from_sandbox",
    "test_list_accounts_from_sandbox",
    "test_list_transactions_from_sandbox",
    "test_list_shared_accounts_from_sandbox",
    "test_get_shared_account_details_from_sandbox",
    "test_list_shared_account_transactions_from_sandbox",
    "test_list_card_bins_from_sandbox",
    "test_list_cards_from_sandbox",
    "test_get_card_cvv_from_sandbox",
    "test_list_card_transactions_from_sandbox",
    "test_get_card_limit_from_sandbox",
    "test_modify_card_limit_from_sandbox",
    "test_get_issue_details_from_sandbox",
    "test_list_card_groups_from_sandbox",
    "test_update_card_group_from_sandbox",
    "test_freeze_card_from_sandbox",
    "test_unfreeze_card_from_sandbox",
    "test_cancel_card_from_sandbox",
    "test_delete_card_group_from_sandbox",
)


def load_tests(loader, tests, pattern):
    """Run the inherited flow in its dependency order."""

    return unittest.TestSuite(
        CardPoolSharedAccountSandboxOpenApiIntegrationTest(test_name)
        for test_name in _TEST_ORDER
    )


if __name__ == "__main__":
    unittest.main()
