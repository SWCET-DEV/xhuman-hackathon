\# demo-payment

PG 결제 API를 호출하는 모듈. payment/retry.py에 charge\_with\_retry(client, order)를 둔다.

client.charge(order\_id, amount, idempotency\_key, timeout)가 응답(status\_code, headers, json())을 돌려준다.

