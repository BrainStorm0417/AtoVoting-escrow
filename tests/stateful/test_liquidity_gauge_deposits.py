import brownie
from brownie import rpc
from brownie.test import strategy


class StateMachine:

    # account to perform a deposit / withdrawal from
    st_account = strategy("address", length=5)

    # amount to deposit / withdraw
    st_value = strategy("uint64")

    # number of weeks to lock a deposit
    st_time = strategy("uint", max_value=86400 * 365)

    def __init__(self, accounts, liquidity_gauge, mock_lp_token):
        self.accounts = accounts
        self.token = mock_lp_token
        self.liquidity_gauge = liquidity_gauge

    def setup(self):
        self.balances = {i: 0 for i in self.accounts}

    def rule_deposit(self, st_account, st_value):
        """
        Make a deposit into the `LiquidityGauge` contract.

        Because of the upper bound of `st_value` relative to the initial account
        balances, this rule should never fail.
        """
        balance = self.token.balanceOf(st_account)

        self.liquidity_gauge.deposit(st_value, {"from": st_account})
        self.balances[st_account] += st_value

        assert self.token.balanceOf(st_account) == balance - st_value

    def rule_withdraw(self, st_account, st_value):
        """
        Attempt to withdraw from the `LiquidityGauge` contract.
        """
        if self.balances[st_account] < st_value:
            # fail path - insufficient balance
            with brownie.reverts():
                self.liquidity_gauge.withdraw(st_value, {"from": st_account})
            return

        # success path
        balance = self.token.balanceOf(st_account)
        self.liquidity_gauge.withdraw(st_value, {"from": st_account})
        self.balances[st_account] -= st_value

        assert self.token.balanceOf(st_account) == balance + st_value

    def rule_advance_time(self, st_time):
        """
        Advance the clock.
        """
        rpc.sleep(st_time)

    def rule_checkpoint(self, st_account):
        """
        Create a new user checkpoint.
        """
        self.liquidity_gauge.user_checkpoint(st_account, {"from": st_account})

    def invariant_balances(self):
        """
        Validate expected balances against actual balances.
        """
        for account, balance in self.balances.items():
            assert self.liquidity_gauge.balanceOf(account) == balance

    def invariant_total_supply(self):
        """
        Validate expected total supply against actual total supply.
        """
        assert self.liquidity_gauge.totalSupply() == sum(self.balances.values())

    def teardown(self):
        """
        Final check to ensure that all balances may be withdrawn.
        """
        for account, balance in ((k, v) for k, v in self.balances.items() if v):
            initial = self.token.balanceOf(account)
            self.liquidity_gauge.withdraw(balance, {"from": account})

            assert self.token.balanceOf(account) == initial + balance


def test_state_machine(
    state_machine, accounts, liquidity_gauge, mock_lp_token, no_call_coverage
):

    for acct in accounts[1:5]:
        mock_lp_token.transfer(acct, 10 ** 21, {"from": accounts[0]})

    for acct in accounts[:5]:
        mock_lp_token.approve(liquidity_gauge, 2 ** 256 - 1, {"from": acct})

    state_machine(
        StateMachine,
        accounts,
        liquidity_gauge,
        mock_lp_token,
        settings={"stateful_step_count": 25},
    )
