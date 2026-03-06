"""Inbound Processor — event-driven task intake for 24/7 autonomous operation.

Instead of waiting for human input, agencies WATCH for incoming work from
multiple channels: API queue, email, webhooks, scheduled tasks, and file drops.
This is what makes an agency a 24/7 autonomous operator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class InboundItem:
    """An incoming work item from any channel."""
    id: str = ""
    source: str = ""  # api, email, webhook, scheduled, file_drop
    task: str = ""
    priority: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InboundChannel:
    """Base class for inbound channels."""

    async def check(self) -> list[InboundItem]:
        """Check for new items. Override in subclasses."""
        return []


class FileDropChannel(InboundChannel):
    """Watches a directory for new files as task inputs."""

    def __init__(self, watch_dir: str = "./inbox", processed_dir: str = "./inbox/processed"):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()

    async def check(self) -> list[InboundItem]:
        items = []
        if not self.watch_dir.exists():
            return items

        for f in self.watch_dir.iterdir():
            if f.is_file() and f.name not in self._seen and not f.name.startswith("."):
                self._seen.add(f.name)
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    items.append(InboundItem(
                        id=f"file-{f.name}",
                        source="file_drop",
                        task=content[:5000],
                        metadata={"filename": f.name, "size": f.stat().st_size},
                    ))
                    # Move to processed (use replace for Windows compatibility)
                    target = self.processed_dir / f.name
                    f.replace(target)
                except Exception as e:
                    logger.warning(f"Failed to process file {f.name}: {e}")

        return items


class APIQueueChannel(InboundChannel):
    """In-memory queue for tasks submitted via API."""

    def __init__(self, api_key: str = "", auth_disabled: bool = False):
        self._queue: asyncio.Queue[InboundItem] = asyncio.Queue()
        self._api_key = api_key
        self._auth_disabled = auth_disabled

    def _verify_key(self, api_key: str | None) -> None:
        """Verify the API key for task submission.

        Raises PermissionError if auth is configured and the key is missing/invalid.
        """
        import hmac
        if self._auth_disabled or not self._api_key:
            return
        if not api_key:
            raise PermissionError("API key required for task submission")
        if not hmac.compare_digest(api_key, self._api_key):
            raise PermissionError("Invalid API key for task submission")

    async def submit(self, task: str, priority: str = "medium", metadata: dict | None = None, *, api_key: str | None = None) -> str:
        """Submit a task to the queue. Returns item ID.

        If the channel has an api_key configured, callers must supply a
        matching ``api_key`` or a ``PermissionError`` is raised.
        """
        self._verify_key(api_key)
        import uuid
        item = InboundItem(
            id=f"api-{uuid.uuid4().hex[:8]}",
            source="api",
            task=task,
            priority=priority,
            metadata=metadata or {},
        )
        await self._queue.put(item)
        return item.id

    async def check(self) -> list[InboundItem]:
        items = []
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                items.append(item)
            except asyncio.QueueEmpty:
                break
        return items


class InboundProcessor:
    """
    Watches for incoming work from multiple channels and processes automatically.

    This is what transforms an agency from "responds when asked" to
    "autonomously processes work 24/7."

    Channels:
    - API queue (tasks submitted via REST API)
    - File drop (text files placed in ./inbox/ directory)
    - Custom channels (webhooks, email, etc.)

    Usage:
        processor = InboundProcessor(agency)
        processor.add_channel("files", FileDropChannel("./inbox"))
        await processor.start()  # Runs forever, processing incoming work
    """

    def __init__(
        self,
        execute_fn: Callable[..., Awaitable[Any]] | None = None,
        poll_interval: float = 10.0,
        max_concurrent: int = 5,
        api_key: str = "",
        auth_disabled: bool = False,
    ):
        self._execute_fn = execute_fn
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self._channels: dict[str, InboundChannel] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._processed_count = 0
        self._failed_count = 0
        self._history: list[dict[str, Any]] = []

        # Default channels
        self._api_queue = APIQueueChannel(api_key=api_key, auth_disabled=auth_disabled)
        self._channels["api"] = self._api_queue
        self._channels["file_drop"] = FileDropChannel()

    def configure_api_auth(self, api_key: str = "", auth_disabled: bool = False) -> None:
        """Configure auth on the built-in API queue channel.

        Useful for post-construction wiring (e.g. from an API server that
        discovers its API key at startup).
        """
        self._api_queue._api_key = api_key
        self._api_queue._auth_disabled = auth_disabled

    def add_channel(self, name: str, channel: InboundChannel) -> None:
        """Add a custom inbound channel."""
        self._channels[name] = channel

    async def submit_task(self, task: str, priority: str = "medium", metadata: dict | None = None, *, api_key: str | None = None) -> str:
        """Submit a task to the API queue.

        If the underlying APIQueueChannel has auth configured, the caller
        must supply a valid ``api_key``.
        """
        return await self._api_queue.submit(task, priority, metadata, api_key=api_key)

    async def start(self) -> None:
        """Start the inbound processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Inbound processor started ({len(self._channels)} channels, poll every {self.poll_interval}s)")

    async def stop(self) -> None:
        """Stop processing."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Inbound processor stopped. Processed: {self._processed_count}, Failed: {self._failed_count}")

    async def _run_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                # Check all channels for new items
                all_items: list[InboundItem] = []
                for name, channel in self._channels.items():
                    try:
                        items = await channel.check()
                        all_items.extend(items)
                    except Exception as e:
                        logger.error(f"Channel '{name}' check failed: {e}")

                # Process items concurrently (up to max_concurrent)
                if all_items:
                    logger.info(f"Processing {len(all_items)} inbound items")
                    tasks = [self._process_item(item) for item in all_items]
                    await asyncio.gather(*tasks, return_exceptions=True)

            except Exception as e:
                logger.error(f"Inbound loop error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _process_item(self, item: InboundItem) -> None:
        """Process a single inbound item through the agency."""
        async with self._semaphore:
            start = time.time()
            logger.info(f"Processing [{item.source}] {item.id}: {item.task[:60]}...")

            try:
                if self._execute_fn:
                    result = await self._execute_fn(
                        task=item.task,
                        context=item.metadata,
                    )
                    success = result.success if hasattr(result, 'success') else True
                    output = result.output if hasattr(result, 'output') else str(result)
                else:
                    success = False
                    output = "No execute function configured"

                duration = time.time() - start
                self._processed_count += 1

                self._history.append({
                    "id": item.id,
                    "source": item.source,
                    "task_preview": item.task[:100],
                    "success": success,
                    "duration_seconds": round(duration, 1),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                if len(self._history) > 1000:
                    self._history = self._history[-1000:]

                logger.info(f"Completed [{item.source}] {item.id}: {'OK' if success else 'FAIL'} ({duration:.1f}s)")

            except Exception as e:
                self._failed_count += 1
                logger.error(f"Failed [{item.source}] {item.id}: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics."""
        return {
            "running": self._running,
            "channels": list(self._channels.keys()),
            "processed": self._processed_count,
            "failed": self._failed_count,
            "recent": self._history[-10:],
        }

    def __repr__(self) -> str:
        return f"InboundProcessor(channels={len(self._channels)}, processed={self._processed_count})"
