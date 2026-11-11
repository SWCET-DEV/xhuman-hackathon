"""PG 결제 API 재시도 정책.

- 멱등키는 주문 ID 로 고정해 모든 재시도에 같은 값을 쓴다 (중복 결제 방지).
- 재시도: 타임아웃·연결 오류, 500/502/503/504.
- 4xx 는 재시도하지 않고 바로 PaymentDeclined(status_code 포함)를 던진다.
- 최대 2회 시도, full jitter 지수 백오프, 전체 마감 시간 안에서만 재시도.
- 마지막 결과가 타임아웃·5xx 이면 결제가 실제로 됐을 수 있으므로
  ChargeOutcomeUnknown 으로 올려 호출 측이 상태 조회/대사를 하게 한다.
"""

import random
import time

MAX_ATTEMPTS = 2
BASE_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 8.0
DEADLINE_SECONDS = 30.0

# TODO: PG사 문서 확인 후 결정. 정해지기 전까지는 호출 시 timeout 을 명시해야 한다.
DEFAULT_TIMEOUT_SECONDS = None

# 클라이언트 라이브러리가 정해지면 그 라이브러리의 타임아웃/연결 예외를 여기에 추가한다.
TRANSIENT_ERRORS = (TimeoutError, ConnectionError)

# 재시도하는 응답. PG 가 요청을 받았을 수 있으므로 끝내 실패하면 결과 불명으로 본다.
RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})


class ChargeError(Exception):
    def __init__(self, message, *, response=None, attempts):
        super().__init__(message)
        self.response = response
        self.attempts = attempts


class ChargeFailed(ChargeError):
    """결제가 되지 않은 것이 확실한 실패."""


class PaymentDeclined(ChargeFailed):
    """PG 가 4xx 로 거절한 결제. 재시도하지 않는다."""

    def __init__(self, message, *, response, attempts):
        super().__init__(message, response=response, attempts=attempts)
        self.status_code = response.status_code


class ChargeOutcomeUnknown(ChargeError):
    """결제 여부를 알 수 없는 실패. 결제 상태 조회 또는 대사가 필요하다."""


def charge_with_retry(
    client,
    order,
    *,
    timeout=None,
    deadline=DEADLINE_SECONDS,
    sleep=time.sleep,
    rand=random.uniform,
    clock=time.monotonic,
):
    timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS
    if timeout is None:
        raise ValueError(
            "PG timeout is not configured: pass timeout= or set DEFAULT_TIMEOUT_SECONDS"
        )

    idempotency_key = f"charge-{order.id}"
    started = clock()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = None
        error = None
        try:
            response = client.charge(order.id, order.amount, idempotency_key, timeout)
        except TRANSIENT_ERRORS as exc:
            error = exc

        if response is not None:
            status = response.status_code
            if 200 <= status < 300:
                return response
            if 400 <= status < 500:
                raise PaymentDeclined(
                    f"PG declined charge with status {status}",
                    response=response,
                    attempts=attempt,
                )
            if status not in RETRYABLE_STATUSES:
                raise ChargeFailed(
                    f"PG rejected charge with status {status}",
                    response=response,
                    attempts=attempt,
                )

        if attempt == MAX_ATTEMPTS:
            break

        cap = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** (attempt - 1))
        delay = rand(0.0, cap)

        elapsed = clock() - started
        if elapsed + delay + timeout > deadline:
            break

        sleep(delay)

    raise ChargeOutcomeUnknown(
        "charge outcome unknown after retries; check payment status",
        response=response,
        attempts=attempt,
    ) from error
