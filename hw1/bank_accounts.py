import csv
import json
import re
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import TypeAlias, TypedDict, cast


class AccountType(str, Enum):
    BASE = "base"
    CHECKING = "checking"
    SAVINGS = "savings"


class OperationType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    INTEREST = "interest"


class OperationStatus(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"


class Operation(TypedDict):
    operation: OperationType
    amount: float
    date: datetime
    balance_after: float
    status: OperationStatus


class HistoryEntry(TypedDict):
    operation: OperationType
    amount: float
    date: str
    balance_after: float
    status: OperationStatus


RawTransaction: TypeAlias = Mapping[str, object]


class Account:
    _account_counter: int = 1000
    account_type: AccountType = AccountType.BASE
    pattern: str = r"[A-Z][a-z]+ [A-Z][a-z]+|[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+"
    allowed_operations: frozenset[OperationType] = frozenset({
        OperationType.DEPOSIT, OperationType.WITHDRAW,
    })

    def __init__(self, account_holder: str, balance: float = 0.0) -> None:
        if not isinstance(account_holder, str) or not re.fullmatch(
            self.pattern, account_holder
        ):
            raise ValueError("Некорректное имя владельца")
        self.__balance: float = self._validate_amount(balance, allow_zero=True)
        self.account_holder: str = account_holder
        self._account_number: str = f"ACC-{Account._account_counter:04d}"
        Account._account_counter += 1
        self._operations_history: list[Operation] = []
        self._pending_history: list[RawTransaction] = []

    @property
    def account_number(self) -> str:
        return self._account_number

    @property
    def operations_history(self) -> list[HistoryEntry]:
        return self.get_history()

    @staticmethod
    def _validate_amount(amount: float, allow_zero: bool = False) -> float:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValueError("Сумма должна быть числом")
        if not isfinite(amount) or amount < 0 or (
            amount == 0 and not allow_zero
        ):
            raise ValueError("Некорректная сумма")
        return float(amount)

    @classmethod
    def _parse_amount(cls, value: object, allow_zero: bool = False) -> float:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("Сумма должна быть числом")
        return cls._validate_amount(float(value), allow_zero)

    def _add_operation(
        self, operation: OperationType, amount: float, status: OperationStatus,
    ) -> None:
        self._operations_history.append({
            "operation": operation,
            "amount": amount,
            "date": datetime.now(),
            "balance_after": self.__balance,
            "status": status,
        })

    def _credit(self, amount: float, operation: OperationType) -> None:
        if not isinstance(operation, OperationType) or (
            operation not in self.allowed_operations
        ) or (
            operation is OperationType.WITHDRAW
        ):
            raise ValueError("Недоступная операция")
        amount = self._validate_amount(
            amount, allow_zero=operation is OperationType.INTEREST
        )
        self.__balance += amount
        self._add_operation(operation, amount, OperationStatus.SUCCESS)

    def deposit(self, amount: float) -> None:
        self._credit(amount, OperationType.DEPOSIT)

    def _withdrawal_limit(self, balance: float) -> float:
        return balance

    def withdraw(self, amount: float) -> bool:
        amount = self._validate_amount(amount)
        success = amount <= self._withdrawal_limit(self.__balance)
        if success:
            self.__balance -= amount
        status = OperationStatus.SUCCESS if success else OperationStatus.FAIL
        self._add_operation(OperationType.WITHDRAW, amount, status)
        return success

    def get_balance(self) -> float:
        return self.__balance

    def get_history(self) -> list[HistoryEntry]:
        return [{
            "operation": operation["operation"],
            "amount": operation["amount"],
            "date": operation["date"].isoformat(sep=" "),
            "balance_after": operation["balance_after"],
            "status": operation["status"],
        } for operation in self._operations_history]

    def get_large_operations(
        self, n: int = 5, min_amount: float = 1000.0,
    ) -> list[HistoryEntry]:
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError("Некорректное количество операций")
        min_amount = self._validate_amount(min_amount, allow_zero=True)
        operations = [operation for operation in self.get_history()
                      if operation["amount"] >= min_amount]
        operations.sort(key=lambda operation: operation["date"], reverse=True)
        return operations[:n]

    def clean_history(self) -> list[Operation]:
        operations: list[Operation] = []
        seen: set[
            tuple[OperationType, float, datetime, float, OperationStatus]
        ] = set()
        for row in self._pending_history:
            try:
                kind = OperationType(row["operation"])
                if kind not in self.allowed_operations:
                    continue
                amount = self._parse_amount(
                    row["amount"], allow_zero=kind is OperationType.INTEREST
                )
                date_value = row["date"]
                if not isinstance(date_value, str):
                    continue
                try:
                    date = datetime.strptime(date_value, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    date = datetime.strptime(date_value, "%d/%m/%Y %H:%M")
                status = OperationStatus(row["status"])
                balance_after = self._parse_amount(
                    row["balance_after"], allow_zero=True
                )
                key = (kind, amount, date, balance_after, status)
                if key in seen:
                    continue
                seen.add(key)
                operations.append({
                    "operation": kind, "amount": amount,
                    "date": date, "status": status,
                    "balance_after": balance_after,
                })
            except (KeyError, TypeError, ValueError, OverflowError):
                continue

        operations.sort(key=lambda operation: operation["date"])
        balance = self.__balance
        cleaned: list[Operation] = []
        for operation in operations:
            if operation["status"] is OperationStatus.SUCCESS:
                if operation["operation"] is OperationType.WITHDRAW:
                    if operation["amount"] > self._withdrawal_limit(balance):
                        continue
                    balance -= operation["amount"]
                else:
                    balance += operation["amount"]
            operation["balance_after"] = balance
            cleaned.append(operation)
        return cleaned

    def load_history(
        self, filename: str | Path, account_number: str | None = None,
    ) -> None:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".json"}:
            raise ValueError("Поддерживаются только CSV и JSON")
        rows: object
        with open(filename, encoding="utf-8-sig", newline="") as file:
            if suffix == ".csv":
                rows = list(csv.DictReader(file))
            else:
                rows = json.load(file)
        if not isinstance(rows, list):
            raise ValueError("История должна быть списком транзакций")
        number = account_number or self.account_number
        self._pending_history = [
            cast(RawTransaction, row) for row in rows
            if isinstance(row, dict)
            and all(isinstance(key, str) for key in row)
            and row.get("account_number") == number
            and row.get("account_type") == self.account_type.value
        ]
        operations = self.clean_history()
        self._operations_history.extend(operations)
        if operations:
            self.__balance = operations[-1]["balance_after"]
        self._pending_history = []


class CheckingAccount(Account):
    account_type: AccountType = AccountType.CHECKING


class SavingsAccount(Account):
    account_type: AccountType = AccountType.SAVINGS
    allowed_operations: frozenset[OperationType] = frozenset({
        OperationType.DEPOSIT, OperationType.WITHDRAW, OperationType.INTEREST,
    })

    def _withdrawal_limit(self, balance: float) -> float:
        return balance / 2

    def withdraw(self, amount: float) -> bool:
        return super().withdraw(amount)

    def apply_interest(self, rate: float) -> None:
        rate = self._validate_amount(rate, allow_zero=True)
        amount = self.get_balance() * rate / 100
        self._credit(amount, OperationType.INTEREST)
