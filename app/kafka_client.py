import asyncio
import json
import logging
from typing import Any, Callable, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from app.config import get_settings
from app.decorators import (
    async_error_handler,
    async_log,
    async_retry,
    langsmith_trace,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class KafkaClient:
    """
    Async Kafka client with Producer, Consumer, DLQ and retry support.
    Designed for KRaft mode (no Zookeeper).
    """

    def __init__(self) -> None:
        self.bootstrap_servers = settings.kafka_bootstrap_servers
        self.producer: Optional[AIOKafkaProducer] = None
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._consumer_task: Optional[asyncio.Task] = None
        self._running = False

    @async_log
    @async_error_handler()
    async def start_producer(self) -> None:
        """Initialize and start the async Kafka producer."""
        if self.producer is not None:
            return

        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",
            enable_idempotence=True,
            compression_type="gzip",
            max_batch_size=16384,
            linger_ms=10,
        )
        await self.producer.start()
        logger.info("Kafka producer started")

    @async_log
    @async_error_handler()
    async def stop_producer(self) -> None:
        if self.producer:
            await self.producer.stop()
            self.producer = None
            logger.info("Kafka producer stopped")

    @async_log
    @async_retry(attempts=3, min_wait=1, max_wait=10, exceptions=(KafkaError,))
    @async_error_handler()
    async def publish(
        self,
        topic: str,
        value: dict[str, Any],
        key: Optional[str] = None,
    ) -> None:
        """
        Publish a message with automatic retry + error handling.
        """
        if self.producer is None:
            await self.start_producer()

        try:
            await self.producer.send_and_wait(topic, value=value, key=key)
            logger.debug(f"Published message to {topic} | key={key}")
        except KafkaError as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            raise

    @async_log
    @async_error_handler()
    async def publish_exception_event(self, event: dict[str, Any]) -> None:
        """Convenience method to publish to the main exceptions topic."""
        key = event.get("order_number") or event.get("thread_id")
        await self.publish(
            topic=settings.kafka_topic_exceptions,
            value=event,
            key=key,
        )

    @async_log
    @async_error_handler()
    async def publish_to_dlq(
        self,
        original_topic: str,
        value: dict[str, Any],
        error: str,
        key: Optional[str] = None,
    ) -> None:
        """Send failed message to Dead Letter Queue."""
        dlq_payload = {
            "original_topic": original_topic,
            "error": error,
            "original_payload": value,
            "failed_at": asyncio.get_event_loop().time(),
        }
        await self.publish(
            topic=settings.kafka_topic_dlq,
            value=dlq_payload,
            key=key,
        )
        logger.warning(f"Message sent to DLQ from topic={original_topic}")

    @async_log
    @async_error_handler()
    async def start_consumer(
        self,
        topic: str,
        group_id: str,
        handler: Callable[[dict[str, Any]], Any],
        auto_offset_reset: str = "earliest",
    ) -> None:
        """
        Start an async consumer that calls the provided handler for each message.
        Includes basic error handling + DLQ support.
        """
        if self.consumer is not None:
            logger.warning("Consumer already running")
            return

        self.consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=False,  # We commit manually after successful processing
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
            max_poll_records=10,
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
        )

        await self.consumer.start()
        self._running = True
        logger.info(f"Kafka consumer started | topic={topic} | group={group_id}")

        self._consumer_task = asyncio.create_task(
            self._consume_loop(topic, handler)
        )

    @async_log
    @async_error_handler()
    async def _consume_loop(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Internal consume loop with error handling and DLQ."""
        try:
            async for msg in self.consumer:
                if not self._running:
                    break

                key = msg.key
                value = msg.value

                try:
                    # Call the business handler (can be async or sync)
                    result = handler(value)
                    if asyncio.iscoroutine(result):
                        await result

                    # Commit only after successful processing
                    await self.consumer.commit()
                    logger.debug(f"Processed message from {topic} | key={key}")

                except Exception as e:
                    logger.exception(f"Error processing message from {topic}: {e}")
                    # Send to DLQ
                    await self.publish_to_dlq(
                        original_topic=topic,
                        value=value,
                        error=str(e),
                        key=key,
                    )
                    # Still commit to avoid infinite reprocessing
                    await self.consumer.commit()

        except Exception as e:
            logger.exception(f"Consumer loop crashed: {e}")
        finally:
            logger.info("Consumer loop ended")

    @async_log
    @async_error_handler()
    async def stop_consumer(self) -> None:
        """Gracefully stop the consumer."""
        self._running = False

        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None

        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
            logger.info("Kafka consumer stopped")

    @async_log
    @async_error_handler()
    async def start(self) -> None:
        """Start producer (consumer is started separately when needed)."""
        await self.start_producer()

    @async_log
    @async_error_handler()
    async def stop(self) -> None:
        """Stop both producer and consumer."""
        await self.stop_consumer()
        await self.stop_producer()


# Global instance
kafka_client = KafkaClient()