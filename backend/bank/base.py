from typing import List, Protocol

from bank.types import BankAccount, NormalizedTxn


class BankProvider(Protocol):
    def list_accounts(self) -> List[BankAccount]:
        ...

    def fetch_transactions(
        self, account_ref: str, date_from: str, date_to: str
    ) -> List[NormalizedTxn]:
        ...
