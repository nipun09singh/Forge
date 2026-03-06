"""Mock data backends for generated domain tools.

When a generated agency has domain-specific tools (e.g., schedule_appointment,
lookup_customer), these mock backends provide realistic fake data so the
tools actually work out of the box — no real integrations needed.

This makes generated agencies immediately functional for demos, testing,
and development. Production deployments can swap in real backends via config.
"""

from __future__ import annotations

import json
import random
import string
import uuid
from datetime import datetime, timedelta
from typing import Any


class MockDataStore:
    """In-memory data store with seed data for common business domains."""

    def __init__(self) -> None:
        self._collections: dict[str, list[dict[str, Any]]] = {}
        self._seed_data_loaded = False

    def _ensure_seed_data(self) -> None:
        if self._seed_data_loaded:
            return
        self._seed_data_loaded = True

        # Seed customers
        self._collections["customers"] = [
            {"id": f"cust_{i:04d}", "name": name, "email": f"{name.lower().replace(' ', '.')}@example.com",
             "phone": f"+1-555-{random.randint(100,999)}-{random.randint(1000,9999)}",
             "plan": random.choice(["free", "starter", "pro", "enterprise"]),
             "created_at": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
             "status": random.choice(["active", "active", "active", "churned"])}
            for i, name in enumerate([
                "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
                "Eva Martinez", "Frank Garcia", "Grace Lee", "Henry Wilson",
                "Iris Taylor", "Jack Anderson", "Kate Thomas", "Leo Jackson",
                "Mia White", "Noah Harris", "Olivia Martin", "Peter Thompson",
            ])
        ]

        # Seed appointments
        self._collections["appointments"] = [
            {"id": f"apt_{uuid.uuid4().hex[:8]}", "customer_id": f"cust_{random.randint(0,15):04d}",
             "date": (datetime.now() + timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d"),
             "time": f"{random.randint(9,17):02d}:{random.choice(['00','30'])}",
             "type": random.choice(["consultation", "support", "onboarding", "review"]),
             "status": "scheduled"}
            for _ in range(8)
        ]

        # Seed tickets
        self._collections["tickets"] = [
            {"id": f"ticket_{i:04d}", "customer_id": f"cust_{random.randint(0,15):04d}",
             "subject": subject, "priority": random.choice(["low", "medium", "high", "urgent"]),
             "status": random.choice(["open", "in_progress", "resolved", "closed"]),
             "created_at": (datetime.now() - timedelta(hours=random.randint(1, 168))).isoformat()}
            for i, subject in enumerate([
                "Can't login to dashboard", "Billing question about Pro plan",
                "Feature request: export to CSV", "API rate limit exceeded",
                "Integration with Slack not working", "Need to upgrade plan",
                "Password reset not receiving email", "Data import failed",
            ])
        ]

        # Seed products
        self._collections["products"] = [
            {"id": f"prod_{i:04d}", "name": name, "price": price,
             "category": cat, "stock": random.randint(0, 500), "status": "active"}
            for i, (name, price, cat) in enumerate([
                ("Pro Plan Monthly", 49.99, "subscription"),
                ("Enterprise Annual", 499.99, "subscription"),
                ("API Access Token", 29.99, "add-on"),
                ("Priority Support", 99.99, "service"),
                ("Custom Integration", 199.99, "service"),
                ("Data Migration", 149.99, "service"),
            ])
        ]

        # Seed orders
        self._collections["orders"] = [
            {"id": f"ord_{uuid.uuid4().hex[:8]}", "customer_id": f"cust_{random.randint(0,15):04d}",
             "product_id": f"prod_{random.randint(0,5):04d}",
             "total": round(random.uniform(29.99, 499.99), 2),
             "status": random.choice(["pending", "completed", "refunded"]),
             "created_at": (datetime.now() - timedelta(days=random.randint(1, 90))).isoformat()}
            for _ in range(12)
        ]

    def query(self, collection: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Query a collection with optional filters."""
        self._ensure_seed_data()
        items = self._collections.get(collection, [])
        if not filters:
            return items
        return [
            item for item in items
            if all(item.get(k) == v for k, v in filters.items())
        ]

    def get_by_id(self, collection: str, item_id: str) -> dict[str, Any] | None:
        """Get a single item by ID."""
        self._ensure_seed_data()
        for item in self._collections.get(collection, []):
            if item.get("id") == item_id:
                return item
        return None

    def create(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new item in a collection."""
        self._ensure_seed_data()
        if collection not in self._collections:
            self._collections[collection] = []
        item_id = f"{collection[:4]}_{uuid.uuid4().hex[:8]}"
        record = {"id": item_id, "created_at": datetime.now().isoformat(), **data}
        self._collections[collection].append(record)
        return record

    def update(self, collection: str, item_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an item by ID."""
        self._ensure_seed_data()
        for item in self._collections.get(collection, []):
            if item.get("id") == item_id:
                item.update(data)
                item["updated_at"] = datetime.now().isoformat()
                return item
        return None

    def delete(self, collection: str, item_id: str) -> bool:
        """Delete an item by ID."""
        self._ensure_seed_data()
        items = self._collections.get(collection, [])
        for i, item in enumerate(items):
            if item.get("id") == item_id:
                items.pop(i)
                return True
        return False


# Global mock data store (shared across all mock tools)
_store = MockDataStore()


def create_mock_tool_function(tool_name: str, description: str, parameters: list[dict]) -> Any:
    """
    Create a functional mock tool function based on the tool's name and parameters.

    Detects the tool's intent from its name and maps to appropriate mock backend operations.
    Returns a real async function that returns realistic mock data.
    """
    # Detect intent from tool name
    name_lower = tool_name.lower()

    # Determine operation type and collection
    operation = "query"  # default
    collection = "customers"  # default

    if any(w in name_lower for w in ["schedule", "book", "appointment", "meeting"]):
        collection = "appointments"
        operation = "create" if any(w in name_lower for w in ["schedule", "book", "create"]) else "query"
    elif any(w in name_lower for w in ["ticket", "issue", "support", "case"]):
        collection = "tickets"
        operation = "create" if any(w in name_lower for w in ["create", "open", "submit"]) else "query"
    elif any(w in name_lower for w in ["customer", "user", "client", "contact"]):
        collection = "customers"
        operation = "query" if any(w in name_lower for w in ["lookup", "search", "find", "get", "list"]) else "create"
    elif any(w in name_lower for w in ["order", "purchase", "transaction"]):
        collection = "orders"
        operation = "query" if any(w in name_lower for w in ["lookup", "search", "find", "get", "list"]) else "create"
    elif any(w in name_lower for w in ["product", "item", "inventory"]):
        collection = "products"
        operation = "query"
    elif any(w in name_lower for w in ["cancel", "delete", "remove"]):
        operation = "delete"
    elif any(w in name_lower for w in ["update", "modify", "change"]):
        operation = "update"

    async def mock_tool_fn(**kwargs: Any) -> str:
        """Mock tool that returns realistic data from the mock data store."""
        try:
            if operation == "query":
                # Build filters from kwargs
                filters = {k: v for k, v in kwargs.items() if v and k != "limit"}
                results = _store.query(collection, filters if filters else None)
                limit = int(kwargs.get("limit", 10))
                results = results[:limit]
                return json.dumps({
                    "success": True,
                    "collection": collection,
                    "count": len(results),
                    "results": results,
                }, indent=2, default=str)

            elif operation == "create":
                record = _store.create(collection, kwargs)
                return json.dumps({
                    "success": True,
                    "message": f"Created new {collection[:-1] if collection.endswith('s') else collection}",
                    "record": record,
                }, indent=2, default=str)

            elif operation == "update":
                item_id = kwargs.pop("id", kwargs.pop("item_id", kwargs.pop(f"{collection[:-1]}_id", "")))
                if item_id:
                    record = _store.update(collection, item_id, kwargs)
                    if record:
                        return json.dumps({"success": True, "updated": record}, indent=2, default=str)
                return json.dumps({"success": False, "error": "Item not found"})

            elif operation == "delete":
                item_id = kwargs.get("id", kwargs.get("item_id", ""))
                deleted = _store.delete(collection, item_id)
                return json.dumps({"success": deleted, "message": "Deleted" if deleted else "Not found"})

            else:
                return json.dumps({"success": True, "data": kwargs, "mock": True})

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    return mock_tool_fn
