"""Independent endpoint contract tests for every enabled controller operation."""

from __future__ import annotations

import unittest
from decimal import Decimal

from luminal_open_api_sdk import (
    CardBinsRequest,
    CardGroupCreateRequest,
    CardGroupDeleteRequest,
    CardGroupRequest,
    CardGroupUpdateRequest,
    CardIdRequest,
    CardLimitUpdateRequest,
    CardTransactionsRequest,
    CreateSharedAccountRequest,
    IssueCardDetailsRequest,
    IssueCardRequest,
    MemberCardPageRequest,
    SharedAccountBalanceRequest,
    SharedAccountGetRequest,
    SharedAccountPageRequest,
    SharedAccountTransactionsRequest,
    WalletInfoRequest,
    WalletTransactionRequest,
    read_private_key,
    read_public_key,
    serialize_json_for_signature,
    verify,
)

from tests.support import (
    PRIVATE_KEY_PEM,
    PUBLIC_KEY_PEM,
    assert_request_contract,
    body_text,
    client_for,
    request_header,
)


class AuthTokenEndpointTest(unittest.TestCase):
    def test_get_token_contract(self) -> None:
        client, opener = client_for({"accessToken": "access"})
        result = client.auth.get_token("app", "secret")
        self.assertEqual("access", result.access_token)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/auth/token",
            "",
            authorization="Basic YXBwOnNlY3JldA==",
        )


class AuthRefreshTokenEndpointTest(unittest.TestCase):
    def test_refresh_token_contract(self) -> None:
        client, opener = client_for({"accessToken": "new"})
        result = client.auth.refresh_token("refresh")
        self.assertEqual("new", result.access_token)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/auth/refresh-token",
            '{"refreshToken":"refresh"}',
        )


class AuthLogoutEndpointTest(unittest.TestCase):
    def test_logout_contract(self) -> None:
        client, opener = client_for(True)
        self.assertTrue(client.auth.logout())
        assert_request_contract(self, opener, "/open-api/v1/auth/logout", "")


class AccountsListEndpointTest(unittest.TestCase):
    def test_list_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"balance": 10.5, "currency": "USD"}]})
        result = client.accounts.list(WalletInfoRequest(page_no=1, page_size=10, currency="USD"))
        self.assertEqual(Decimal("10.5"), result.list[0].balance)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/accounts",
            '{"currency":"USD","pageNo":1,"pageSize":10}',
        )


class TransactionsListEndpointTest(unittest.TestCase):
    def test_list_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"orderNo": "O1"}]})
        result = client.transactions.list(WalletTransactionRequest(page_no=1, page_size=10))
        self.assertEqual("O1", result.list[0].order_no)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/transactions/list",
            '{"pageNo":1,"pageSize":10}',
        )


class SharedAccountCreateEndpointTest(unittest.TestCase):
    def test_create_contract(self) -> None:
        client, opener = client_for({"memberSharedAccountId": 7})
        result = client.shared_accounts.create(CreateSharedAccountRequest(2, Decimal("10.00"), "Travel"))
        self.assertEqual(7, result.member_shared_account_id)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/shared-account/create",
            '{"accountName":"Travel","cardBinId":2,"rechargeAmount":10.00}',
        )


class SharedAccountListEndpointTest(unittest.TestCase):
    def test_list_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"accountName": "Travel"}], "extra": None})
        result = client.shared_accounts.list(SharedAccountPageRequest(page_no=1, page_size=10))
        self.assertEqual("Travel", result.list[0].account_name)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/shared-account/list",
            '{"pageNo":1,"pageSize":10}',
        )


class SharedAccountIncreaseEndpointTest(unittest.TestCase):
    def test_increase_contract(self) -> None:
        client, opener = client_for({"sharedAccountTransactionId": "tx-1"})
        result = client.shared_accounts.increase(SharedAccountBalanceRequest(7, Decimal("5.00")))
        self.assertEqual("tx-1", result.shared_account_transaction_id)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/shared-account/increase",
            '{"amount":5.00,"memberSharedAccountId":7}',
        )


class SharedAccountDecreaseEndpointTest(unittest.TestCase):
    def test_decrease_contract(self) -> None:
        client, opener = client_for({"sharedAccountTransactionId": "tx-2"})
        result = client.shared_accounts.decrease(SharedAccountBalanceRequest(7, Decimal("2.00")))
        self.assertEqual("tx-2", result.shared_account_transaction_id)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/shared-account/decrease",
            '{"amount":2.00,"memberSharedAccountId":7}',
        )


class SharedAccountDetailsEndpointTest(unittest.TestCase):
    def test_details_contract(self) -> None:
        client, opener = client_for({"memberSharedAccountId": 7, "accountName": "Travel"})
        result = client.shared_accounts.details(SharedAccountGetRequest(7))
        self.assertEqual("Travel", result.account_name)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/shared-account/details",
            '{"memberSharedAccountId":7}',
        )


class SharedAccountTransactionsEndpointTest(unittest.TestCase):
    def test_transactions_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"sharedAccountTransactionId": 1}], "extra": None})
        result = client.shared_accounts.transactions(SharedAccountTransactionsRequest(page_no=1, page_size=10))
        self.assertEqual(1, result.list[0].shared_account_transaction_id)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/shared-account/transactions",
            '{"pageNo":1,"pageSize":10}',
        )


class CardBinsEndpointTest(unittest.TestCase):
    def test_bins_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"cardBin": "123456"}], "extra": None})
        request = CardBinsRequest(1, 10, "SHARED", "VISA", "123456", "US")
        result = client.cards.bins(request)
        self.assertEqual("123456", result.list[0].card_bin)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/bins",
            '{"areaCode":"US","cardBin":"123456","cardOrganization":"VISA","cardType":"SHARED","pageNo":1,"pageSize":10}',
        )


class CardIssueEndpointTest(unittest.TestCase):
    def test_issue_contract(self) -> None:
        client, opener = client_for(501)
        request = IssueCardRequest(1, 2, 3, "Travel", "SHARED", 4, None, Decimal("100.00"))
        self.assertEqual(501, client.cards.issue(request, "precomputed-signature"))
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/issue",
            '{"applyCount":1,"cardBinId":2,"cardGroupId":3,"cardName":"Travel","cardType":"SHARED","memberSharedAccountId":4,"rechargeAmount":100.00}',
            signature="precomputed-signature",
        )

    def test_private_key_signs_numeric_long_json_but_sends_normal_body(self) -> None:
        client, opener = client_for(501)
        request = IssueCardRequest(
            1,
            2_064_991_632_710_991_874,
            3,
            "Travel",
            "SHARED",
            4,
            None,
            Decimal("100.00"),
        )

        self.assertEqual(501, client.cards.issue(request, read_private_key(PRIVATE_KEY_PEM)))
        transmitted = body_text(opener).encode()
        signing = serialize_json_for_signature(request)
        signature = request_header(opener, "sign")

        self.assertIn(b'"cardBinId":"2064991632710991874"', transmitted)
        self.assertIn(b'"cardBinId":2064991632710991874', signing)
        self.assertNotEqual(transmitted, signing)
        self.assertTrue(verify(signing, signature, read_public_key(PUBLIC_KEY_PEM)))
        self.assertFalse(verify(transmitted, signature, read_public_key(PUBLIC_KEY_PEM)))

    def test_decodes_large_task_id_as_java_long(self) -> None:
        client, _ = client_for("2064991632710991874")
        request = IssueCardRequest(1, 2, 3, "Travel", "SHARED", 4, None, Decimal("100.00"))
        self.assertEqual(2_064_991_632_710_991_874, client.cards.issue(request, "precomputed-signature"))


class CardListEndpointTest(unittest.TestCase):
    def test_list_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"memberCardId": 5, "status": "ACTIVE"}], "extra": None})
        request = MemberCardPageRequest(1, 10, 5, "ACTIVE", None, "SHARED", None, [3])
        result = client.cards.list(request)
        self.assertEqual(5, result.list[0].member_card_id)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/list",
            '{"cardGroups":[3],"cardType":"SHARED","memberCardId":5,"pageNo":1,"pageSize":10,"status":"ACTIVE"}',
        )


class CardCvvEndpointTest(unittest.TestCase):
    def test_cvv_contract(self) -> None:
        client, opener = client_for({"memberCardId": 5, "cvv": "123", "cardNo": "4111", "expiryDate": "2030-01"})
        result = client.cards.cvv(CardIdRequest(5))
        self.assertEqual("123", result.cvv)
        assert_request_contract(self, opener, "/open-api/v1/cards/cvv", '{"memberCardId":5}')


class CardTransactionsEndpointTest(unittest.TestCase):
    def test_transactions_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"orderNo": "O1"}], "extra": None})
        result = client.cards.transactions(CardTransactionsRequest(1, 10, "SHARED", 5, [1, 2]))
        self.assertEqual("O1", result.list[0].order_no)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/transactions",
            '{"cardType":"SHARED","memberCardId":5,"pageNo":1,"pageSize":10,"tradeTime":[1,2]}',
        )


class CardLimitEndpointTest(unittest.TestCase):
    def test_limit_contract(self) -> None:
        client, opener = client_for({"memberCardId": 5, "totalLimit": 100, "balance": 80})
        result = client.cards.limit(CardIdRequest(5))
        self.assertEqual(Decimal("100"), result.total_limit)
        assert_request_contract(self, opener, "/open-api/v1/cards/limit", '{"memberCardId":5}')


class CardLimitModifyEndpointTest(unittest.TestCase):
    def test_modify_limit_contract(self) -> None:
        client, opener = client_for(True)
        self.assertTrue(client.cards.modify_limit(CardLimitUpdateRequest(5, Decimal("10"))))
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/limit/modify",
            '{"memberCardId":5,"totalLimit":10}',
        )


class CardFreezeEndpointTest(unittest.TestCase):
    def test_freeze_contract(self) -> None:
        client, opener = client_for(True)
        self.assertTrue(client.cards.freeze(CardIdRequest(5)))
        assert_request_contract(self, opener, "/open-api/v1/cards/freeze", '{"memberCardId":5}')


class CardUnfreezeEndpointTest(unittest.TestCase):
    def test_unfreeze_contract(self) -> None:
        client, opener = client_for(True)
        self.assertTrue(client.cards.unfreeze(CardIdRequest(5)))
        assert_request_contract(self, opener, "/open-api/v1/cards/unfreeze", '{"memberCardId":5}')


class CardCancelEndpointTest(unittest.TestCase):
    def test_cancel_contract(self) -> None:
        client, opener = client_for(True)
        self.assertTrue(client.cards.cancel(CardIdRequest(5)))
        assert_request_contract(self, opener, "/open-api/v1/cards/cancel", '{"memberCardId":5}')


class CardIssueDetailsEndpointTest(unittest.TestCase):
    def test_issue_details_contract(self) -> None:
        client, opener = client_for([{"memberCardId": 5, "cardStatus": "ACTIVE", "message": "created"}])
        result = client.cards.issue_details(IssueCardDetailsRequest(501))
        self.assertEqual("created", result[0].message)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/issue/detail",
            '{"taskId":501}',
        )


class CardGroupListEndpointTest(unittest.TestCase):
    def test_list_contract(self) -> None:
        client, opener = client_for({"total": 1, "list": [{"cardGroupId": 4, "cardGroupName": "Travel"}], "extra": None})
        result = client.card_groups.list(CardGroupRequest(1, 10, "SHARED"))
        self.assertEqual("Travel", result.list[0].card_group_name)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/group",
            '{"cardType":"SHARED","pageNo":1,"pageSize":10}',
        )


class CardGroupCreateEndpointTest(unittest.TestCase):
    def test_create_contract(self) -> None:
        client, opener = client_for({"cardGroupId": 4, "cardGroupName": "Travel"})
        result = client.card_groups.create(CardGroupCreateRequest("Travel", "SHARED"))
        self.assertEqual(4, result.card_group_id)
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/group/create",
            '{"cardGroupName":"Travel","cardType":"SHARED"}',
        )


class CardGroupUpdateEndpointTest(unittest.TestCase):
    def test_update_contract(self) -> None:
        client, opener = client_for(True)
        self.assertTrue(client.card_groups.update(CardGroupUpdateRequest(4, "Trips")))
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/group/update",
            '{"cardGroupId":4,"cardGroupName":"Trips"}',
        )


class CardGroupDeleteEndpointTest(unittest.TestCase):
    def test_delete_contract(self) -> None:
        client, opener = client_for(True)
        self.assertTrue(client.card_groups.delete(CardGroupDeleteRequest(4)))
        assert_request_contract(
            self,
            opener,
            "/open-api/v1/cards/group/delete",
            '{"cardGroupId":4}',
        )


if __name__ == "__main__":
    unittest.main()
