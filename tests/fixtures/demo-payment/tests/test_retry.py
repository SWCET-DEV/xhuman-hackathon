from dataclasses import dataclass, field

import pytest

from payment.retry import (
    ChargeFailed,
    ChargeOutcomeUnknown,
    PaymentDeclined,
    charge_with_retry,
)


# ---------------------------------------------------------------------------
# 테스트 도우미
# ---------------------------------------------------------------------------


@dataclass
class Order:
    id: str = "order-1"
    amount: int = 10_000


@dataclass
class FakeResponse:
    status_code: int
    headers: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)

    def json(self):
        return self.body


class FakeClient:
    """미리 정해 둔 결과(응답 또는 예외)를 순서대로 돌려주는 PG 클라이언트."""

    def __init__(self, outcomes, clock=None, call_duration=0.0):
        self._outcomes = list(outcomes)
        self._clock = clock
        self._call_duration = call_duration
        self.calls = []

    def charge(self, order_id, amount, idempotency_key, timeout):
        self.calls.append(
            dict(
                order_id=order_id,
                amount=amount,
                idempotency_key=idempotency_key,
                timeout=timeout,
            )
        )
        if self._clock is not None:
            self._clock.advance(self._call_duration)
        # 준비한 결과보다 많이 호출되면 마지막 결과를 반복한다.
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def upper_bound(low, high):
    """jitter 를 없애고 상한값을 그대로 쓰는 난수 함수."""
    return high


def run(client, clock=None, **kwargs):
    clock = clock or FakeClock()
    kwargs.setdefault("timeout", 10.0)
    return charge_with_retry(
        client,
        Order(),
        sleep=clock.sleep,
        rand=upper_bound,
        clock=clock,
        **kwargs,
    )


def ok():
    return FakeResponse(200, body={"result": "approved"})


TRANSIENT_OUTCOMES = [
    pytest.param(lambda: FakeResponse(500), id="500"),
    pytest.param(lambda: FakeResponse(502), id="502"),
    pytest.param(lambda: FakeResponse(503), id="503"),
    pytest.param(lambda: FakeResponse(504), id="504"),
    pytest.param(lambda: TimeoutError("read timed out"), id="timeout"),
    pytest.param(lambda: ConnectionError("connection reset"), id="connection-error"),
]


# ---------------------------------------------------------------------------
# 최대 2회 시도
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("make_outcome", TRANSIENT_OUTCOMES)
def test_gives_up_after_exactly_two_attempts_on_transient_failure(make_outcome):
    client = FakeClient([make_outcome()])

    with pytest.raises(ChargeOutcomeUnknown):
        run(client)

    assert len(client.calls) == 2


def test_succeeds_on_second_and_final_attempt():
    client = FakeClient([TimeoutError(), ok()])

    response = run(client)

    assert response.status_code == 200
    assert len(client.calls) == 2


def test_never_makes_a_third_attempt_even_when_it_would_succeed():
    client = FakeClient([FakeResponse(503), FakeResponse(503), ok()])

    with pytest.raises(ChargeOutcomeUnknown):
        run(client)

    assert len(client.calls) == 2


# ---------------------------------------------------------------------------
# 성공 / 재시도
# ---------------------------------------------------------------------------


def test_returns_response_on_first_success_without_sleeping():
    clock = FakeClock()
    client = FakeClient([ok()])

    response = run(client, clock)

    assert response.json() == {"result": "approved"}
    assert len(client.calls) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize("make_outcome", TRANSIENT_OUTCOMES)
def test_retries_transient_failure_then_succeeds(make_outcome):
    client = FakeClient([make_outcome(), ok()])

    response = run(client)

    assert response.status_code == 200
    assert len(client.calls) == 2


# ---------------------------------------------------------------------------
# 재시도하지 않는 응답
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 409, 422, 429, 499])
def test_raises_payment_declined_without_retry_on_any_4xx(status):
    response = FakeResponse(status, body={"code": "card_declined"})
    client = FakeClient([response, ok()])

    with pytest.raises(PaymentDeclined) as excinfo:
        run(client)

    assert len(client.calls) == 1
    assert excinfo.value.status_code == status
    assert excinfo.value.response is response


def test_payment_declined_is_a_definite_failure():
    client = FakeClient([FakeResponse(402)])

    with pytest.raises(ChargeFailed):
        run(client)


def test_unexpected_non_4xx_status_is_a_definite_failure_but_not_a_decline():
    client = FakeClient([FakeResponse(501)])

    with pytest.raises(ChargeFailed) as excinfo:
        run(client)

    assert not isinstance(excinfo.value, PaymentDeclined)
    assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# 멱등키 / 요청 인자
# ---------------------------------------------------------------------------


def test_reuses_same_idempotency_key_across_all_attempts():
    client = FakeClient([TimeoutError(), ok()])

    run(client)

    keys = {call["idempotency_key"] for call in client.calls}
    assert keys == {"charge-order-1"}


def test_passes_order_id_amount_and_timeout_to_client():
    client = FakeClient([ok()])

    run(client, timeout=7.5)

    assert client.calls == [
        dict(
            order_id="order-1",
            amount=10_000,
            idempotency_key="charge-order-1",
            timeout=7.5,
        )
    ]


def test_refuses_to_call_pg_when_timeout_is_not_configured():
    client = FakeClient([ok()])

    with pytest.raises(ValueError, match="timeout"):
        charge_with_retry(client, Order())

    assert client.calls == []


# ---------------------------------------------------------------------------
# 대기 시간
# ---------------------------------------------------------------------------


def test_backs_off_exponentially_between_attempts():
    clock = FakeClock()
    client = FakeClient([FakeResponse(503)])

    with pytest.raises(ChargeOutcomeUnknown):
        run(client, clock)

    # 시도 사이에만 쉰다: 0.5 * 2^0 (rand 는 상한값을 돌려준다)
    assert clock.sleeps == [0.5]


def test_backoff_is_drawn_from_zero_to_the_exponential_cap():
    bounds = []

    def record(low, high):
        bounds.append((low, high))
        return 0.0

    clock = FakeClock()
    client = FakeClient([FakeResponse(503)])

    with pytest.raises(ChargeOutcomeUnknown):
        charge_with_retry(
            client, Order(), timeout=10.0, sleep=clock.sleep, rand=record, clock=clock
        )

    assert bounds == [(0.0, 0.5)]


# ---------------------------------------------------------------------------
# 전체 마감 시간
# ---------------------------------------------------------------------------


def test_skips_remaining_attempts_when_next_one_would_exceed_deadline():
    clock = FakeClock()
    # 호출 한 번에 14초씩 걸리는 느린 PG
    client = FakeClient([TimeoutError()], clock=clock, call_duration=14.0)

    with pytest.raises(ChargeOutcomeUnknown):
        run(client, clock, timeout=10.0, deadline=20.0)

    # 1회차 후 14s: 14 + 0.5 + 10 > 20 → 2회차를 시도하지 않고 중단
    assert len(client.calls) == 1


def test_unknown_outcome_carries_last_error_for_reconciliation():
    client = FakeClient([TimeoutError("read timed out")])

    with pytest.raises(ChargeOutcomeUnknown) as excinfo:
        run(client)

    assert isinstance(excinfo.value.__cause__, TimeoutError)
    assert excinfo.value.attempts == 2
