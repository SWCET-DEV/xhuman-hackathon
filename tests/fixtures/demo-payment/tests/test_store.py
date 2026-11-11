import json
import sqlite3
from dataclasses import dataclass, field

import pytest

from payment.store import create_payments_table, record_payment


@dataclass
class Order:
    id: str = "order-1"
    amount: int = 10_000


@dataclass
class FakeResponse:
    status_code: int = 200
    body: dict = field(default_factory=lambda: {"tid": "pg-123", "result": "approved"})
    headers: dict = field(default_factory=dict)

    def json(self):
        return self.body


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    create_payments_table(conn)
    yield conn
    conn.close()


def rows(conn):
    cur = conn.execute(
        "SELECT order_id, amount, status_code, response_json FROM payments ORDER BY id"
    )
    return cur.fetchall()


def test_records_successful_payment(conn):
    record_payment(conn, Order(), FakeResponse())

    [(order_id, amount, status_code, response_json)] = rows(conn)
    assert order_id == "order-1"
    assert amount == 10_000
    assert status_code == 200
    assert json.loads(response_json) == {"tid": "pg-123", "result": "approved"}


def test_sets_created_at(conn):
    record_payment(conn, Order(), FakeResponse())

    [(created_at,)] = conn.execute("SELECT created_at FROM payments").fetchall()
    assert created_at


def test_returns_true_when_a_row_is_inserted(conn):
    assert record_payment(conn, Order(), FakeResponse()) is True


def test_does_not_record_the_same_order_twice(conn):
    record_payment(conn, Order(), FakeResponse())

    inserted = record_payment(conn, Order(), FakeResponse(body={"tid": "pg-999"}))

    assert inserted is False
    [(_, _, _, response_json)] = rows(conn)
    assert json.loads(response_json)["tid"] == "pg-123"


def test_records_different_orders_separately(conn):
    record_payment(conn, Order(id="order-1"), FakeResponse())
    record_payment(conn, Order(id="order-2", amount=5_000), FakeResponse())

    assert [(r[0], r[1]) for r in rows(conn)] == [("order-1", 10_000), ("order-2", 5_000)]


@pytest.mark.parametrize("status", [402, 500, 503])
def test_refuses_to_record_unsuccessful_response(conn, status):
    with pytest.raises(ValueError, match="status"):
        record_payment(conn, Order(), FakeResponse(status_code=status))

    assert rows(conn) == []


def test_record_is_committed_and_visible_from_another_connection(tmp_path):
    path = tmp_path / "payments.db"
    writer = sqlite3.connect(path)
    create_payments_table(writer)

    record_payment(writer, Order(), FakeResponse())

    reader = sqlite3.connect(path)
    try:
        [(order_id,)] = reader.execute("SELECT order_id FROM payments").fetchall()
        assert order_id == "order-1"
    finally:
        reader.close()
        writer.close()


def test_create_payments_table_is_safe_to_call_twice(conn):
    create_payments_table(conn)

    record_payment(conn, Order(), FakeResponse())
    assert len(rows(conn)) == 1
