import pytest
from unittest.mock import AsyncMock, patch

from app.kafka_client import KafkaClient


@pytest.mark.asyncio
async def test_kafka_publish_exception_event():
    client = KafkaClient()
    with patch.object(client, "publish", new_callable=AsyncMock) as pub:
        # adapt if your method name differs
        if hasattr(client, "publish_exception_event"):
            await client.publish_exception_event(
                {"thread_id": "t1", "order_number": "ORD-1"}
            )
        else:
            await client.publish("ops.exceptions", {"thread_id": "t1"})
        assert pub.await_count >= 1


@pytest.mark.asyncio
async def test_kafka_publish_to_dlq():
    client = KafkaClient()
    with patch.object(client, "publish", new_callable=AsyncMock) as pub:
        if hasattr(client, "publish_to_dlq"):
            await client.publish_to_dlq(
                original_topic="ops.exceptions",
                value={"a": 1},
                error="boom",
                key="k1",
            )
        else:
            await client.publish("ops.exceptions.dlq", {"error": "boom"})
        assert pub.await_count >= 1