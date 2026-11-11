"""성공한 결제를 sqlite payments 테이블에 기록한다."""

import json

_CREATE_PAYMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS payments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      TEXT    NOT NULL UNIQUE,
    amount        INTEGER NOT NULL,
    status_code   INTEGER NOT NULL,
    response_json TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_INSERT_PAYMENT = """
INSERT INTO payments (order_id, amount, status_code, response_json)
VALUES (?, ?, ?, ?)
ON CONFLICT(order_id) DO NOTHING
"""


def create_payments_table(conn):
    with conn:
        conn.execute(_CREATE_PAYMENTS_TABLE)


def record_payment(conn, order, response):
    """성공한 결제 1건을 기록하고 커밋한다.

    같은 주문이 이미 기록돼 있으면 덮어쓰지 않고 False 를 돌려준다
    (기록 단계를 다시 실행해도 행이 중복되지 않는다).
    """
    status = response.status_code
    if not 200 <= status < 300:
        raise ValueError(f"refusing to record unsuccessful payment: status {status}")

    with conn:
        cur = conn.execute(
            _INSERT_PAYMENT,
            (
                order.id,
                order.amount,
                status,
                json.dumps(response.json(), ensure_ascii=False),
            ),
        )
    return cur.rowcount == 1
