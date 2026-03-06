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


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------

def detect_domain(agency_name: str, description: str = "") -> str:
    """Guess the business domain from agency name/description via keyword matching.

    Returns one of: healthcare, education, ecommerce, saas_support, real_estate,
    legal, or "default" when no strong signal is found.
    """
    text = f"{agency_name} {description}".lower()

    _keywords: dict[str, list[str]] = {
        "healthcare": [
            "health", "medical", "patient", "doctor", "clinic", "hospital",
            "pharmacy", "diagnosis", "prescription", "nurse", "therapeutic",
            "dental", "surgery", "cardio", "radiology", "oncology",
        ],
        "education": [
            "school", "university", "college", "student", "teacher", "course",
            "grade", "enrollment", "academic", "tutor", "professor", "campus",
            "curriculum", "semester", "lecture", "degree",
        ],
        "ecommerce": [
            "shop", "store", "retail", "cart", "shipping", "inventory",
            "merchandise", "warehouse", "fulfillment", "marketplace",
            "catalog", "checkout", "ecommerce", "e-commerce",
        ],
        "saas_support": [
            "saas", "software", "subscription", "helpdesk", "ticket",
            "onboarding", "api", "platform", "dashboard", "integration",
            "tenant", "cloud service",
        ],
        "real_estate": [
            "real estate", "property", "listing", "house", "apartment",
            "rental", "mortgage", "realtor", "broker", "housing",
            "condo", "lease", "landlord", "realty",
        ],
        "legal": [
            "law", "legal", "attorney", "court", "litigation", "contract",
            "paralegal", "counsel", "judge", "verdict", "plaintiff",
            "defendant", "deposition", "arbitration", "compliance",
        ],
    }

    scores = {d: sum(1 for kw in kws if kw in text) for d, kws in _keywords.items()}
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else "default"


# ---------------------------------------------------------------------------
# Domain seed-data factories
# ---------------------------------------------------------------------------

def _seed_default() -> dict[str, list[dict[str, Any]]]:
    """Generic / default seed data (original behaviour)."""
    c: dict[str, list[dict[str, Any]]] = {}

    c["customers"] = [
        {"id": f"cust_{i:04d}", "name": name,
         "email": f"{name.lower().replace(' ', '.')}@example.com",
         "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
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

    c["appointments"] = [
        {"id": f"apt_{uuid.uuid4().hex[:8]}",
         "customer_id": f"cust_{random.randint(0, 15):04d}",
         "date": (datetime.now() + timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d"),
         "time": f"{random.randint(9, 17):02d}:{random.choice(['00', '30'])}",
         "type": random.choice(["consultation", "support", "onboarding", "review"]),
         "status": "scheduled"}
        for _ in range(8)
    ]

    c["tickets"] = [
        {"id": f"ticket_{i:04d}",
         "customer_id": f"cust_{random.randint(0, 15):04d}",
         "subject": subject,
         "priority": random.choice(["low", "medium", "high", "urgent"]),
         "status": random.choice(["open", "in_progress", "resolved", "closed"]),
         "created_at": (datetime.now() - timedelta(hours=random.randint(1, 168))).isoformat()}
        for i, subject in enumerate([
            "Can't login to dashboard", "Billing question about Pro plan",
            "Feature request: export to CSV", "API rate limit exceeded",
            "Integration with Slack not working", "Need to upgrade plan",
            "Password reset not receiving email", "Data import failed",
        ])
    ]

    c["products"] = [
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

    c["orders"] = [
        {"id": f"ord_{uuid.uuid4().hex[:8]}",
         "customer_id": f"cust_{random.randint(0, 15):04d}",
         "product_id": f"prod_{random.randint(0, 5):04d}",
         "total": round(random.uniform(29.99, 499.99), 2),
         "status": random.choice(["pending", "completed", "refunded"]),
         "created_at": (datetime.now() - timedelta(days=random.randint(1, 90))).isoformat()}
        for _ in range(12)
    ]

    return c


def _seed_healthcare() -> dict[str, list[dict[str, Any]]]:
    """Healthcare domain seed data."""
    c: dict[str, list[dict[str, Any]]] = {}

    c["patients"] = [
        {"id": f"pat_{i:04d}", "name": name,
         "date_of_birth": f"{random.randint(1950, 2005)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
         "blood_type": random.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
         "insurance_provider": random.choice(["BlueCross", "Aetna", "UnitedHealth", "Cigna", "Kaiser"]),
         "conditions": random.sample(["hypertension", "diabetes", "asthma", "allergies", "none"], k=random.randint(1, 2)),
         "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
         "status": random.choice(["active", "active", "active", "inactive"])}
        for i, name in enumerate([
            "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
            "Eva Martinez", "Frank Garcia", "Grace Lee", "Henry Wilson",
            "Iris Taylor", "Jack Anderson", "Kate Thomas", "Leo Jackson",
            "Mia White", "Noah Harris", "Olivia Martin", "Peter Thompson",
        ])
    ]

    c["doctors"] = [
        {"id": f"doc_{i:04d}", "name": name, "specialty": spec,
         "license_number": f"MD-{random.randint(100000, 999999)}",
         "department": dept, "status": "active"}
        for i, (name, spec, dept) in enumerate([
            ("Dr. Sarah Chen", "cardiology", "Cardiology"),
            ("Dr. James Rivera", "orthopedics", "Orthopedics"),
            ("Dr. Priya Patel", "pediatrics", "Pediatrics"),
            ("Dr. Michael Okafor", "general practice", "General Medicine"),
            ("Dr. Lisa Yamamoto", "dermatology", "Dermatology"),
            ("Dr. Robert Kim", "neurology", "Neurology"),
            ("Dr. Angela Torres", "oncology", "Oncology"),
            ("Dr. William Shah", "surgery", "Surgery"),
        ])
    ]

    c["appointments"] = [
        {"id": f"apt_{uuid.uuid4().hex[:8]}",
         "patient_id": f"pat_{random.randint(0, 15):04d}",
         "doctor_id": f"doc_{random.randint(0, 7):04d}",
         "date": (datetime.now() + timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d"),
         "time": f"{random.randint(8, 17):02d}:{random.choice(['00', '15', '30', '45'])}",
         "type": random.choice(["checkup", "consultation", "surgery", "follow-up"]),
         "status": random.choice(["scheduled", "confirmed", "completed"])}
        for _ in range(8)
    ]

    c["medical_records"] = [
        {"id": f"rec_{uuid.uuid4().hex[:8]}",
         "patient_id": f"pat_{random.randint(0, 15):04d}",
         "doctor_id": f"doc_{random.randint(0, 7):04d}",
         "date": (datetime.now() - timedelta(days=random.randint(1, 180))).strftime("%Y-%m-%d"),
         "diagnosis": diag, "prescriptions": rx,
         "notes": "Patient responded well to treatment."}
        for diag, rx in [
            ("Hypertension Stage 1", ["Lisinopril 10mg", "Low-sodium diet"]),
            ("Type 2 Diabetes", ["Metformin 500mg", "Blood sugar monitoring"]),
            ("Seasonal Allergies", ["Cetirizine 10mg"]),
            ("Lower Back Pain", ["Ibuprofen 400mg", "Physical therapy referral"]),
            ("Upper Respiratory Infection", ["Amoxicillin 500mg", "Rest and fluids"]),
            ("Mild Concussion", ["Acetaminophen", "Cognitive rest"]),
            ("Eczema", ["Hydrocortisone cream", "Moisturizer"]),
            ("Anxiety Disorder", ["Sertraline 50mg", "CBT referral"]),
        ]
    ]

    return c


def _seed_education() -> dict[str, list[dict[str, Any]]]:
    """Education domain seed data."""
    c: dict[str, list[dict[str, Any]]] = {}

    c["students"] = [
        {"id": f"stu_{i:04d}", "name": name,
         "email": f"{name.lower().replace(' ', '.')}@university.edu",
         "major": random.choice(["Computer Science", "Biology", "English", "Mathematics", "History", "Psychology"]),
         "gpa": round(random.uniform(2.0, 4.0), 2),
         "enrollment_year": random.choice([2021, 2022, 2023, 2024]),
         "status": random.choice(["enrolled", "enrolled", "enrolled", "on_leave"])}
        for i, name in enumerate([
            "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
            "Eva Martinez", "Frank Garcia", "Grace Lee", "Henry Wilson",
            "Iris Taylor", "Jack Anderson", "Kate Thomas", "Leo Jackson",
            "Mia White", "Noah Harris", "Olivia Martin", "Peter Thompson",
        ])
    ]

    c["teachers"] = [
        {"id": f"tch_{i:04d}", "name": name, "department": dept,
         "email": f"{name.lower().split()[-1]}@university.edu",
         "office": f"Hall {chr(65 + i)}, Room {random.randint(100, 400)}",
         "status": "active"}
        for i, (name, dept) in enumerate([
            ("Prof. Margaret Liu", "Computer Science"),
            ("Prof. Robert Hayes", "Mathematics"),
            ("Prof. Sandra Okonkwo", "Biology"),
            ("Prof. David Schneider", "History"),
            ("Prof. Karen Alvarez", "English"),
            ("Prof. Thomas Park", "Psychology"),
            ("Prof. Jennifer Walsh", "Physics"),
            ("Prof. Ahmed Hassan", "Chemistry"),
        ])
    ]

    c["courses"] = [
        {"id": f"crs_{i:04d}", "name": name, "code": code,
         "department": dept, "credits": credits,
         "instructor_id": f"tch_{random.randint(0, 7):04d}",
         "schedule": random.choice(["MWF 9:00-9:50", "TTh 10:30-11:45", "MWF 13:00-13:50", "TTh 14:00-15:15"])}
        for i, (name, code, dept, credits) in enumerate([
            ("Intro to Computer Science", "CS101", "Computer Science", 3),
            ("Data Structures", "CS201", "Computer Science", 4),
            ("Calculus I", "MATH101", "Mathematics", 4),
            ("General Biology", "BIO101", "Biology", 3),
            ("World History", "HIST101", "History", 3),
            ("Creative Writing", "ENG201", "English", 3),
            ("Intro to Psychology", "PSY101", "Psychology", 3),
            ("Organic Chemistry", "CHEM201", "Chemistry", 4),
        ])
    ]

    c["enrollments"] = [
        {"id": f"enr_{uuid.uuid4().hex[:8]}",
         "student_id": f"stu_{random.randint(0, 15):04d}",
         "course_id": f"crs_{random.randint(0, 7):04d}",
         "semester": random.choice(["Fall 2024", "Spring 2025"]),
         "status": random.choice(["enrolled", "enrolled", "completed", "dropped"]),
         "grade": random.choice(["A", "A-", "B+", "B", "B-", "C+", None])}
        for _ in range(12)
    ]

    c["grades"] = [
        {"id": f"grd_{uuid.uuid4().hex[:8]}",
         "student_id": f"stu_{random.randint(0, 15):04d}",
         "course_id": f"crs_{random.randint(0, 7):04d}",
         "assignment": assignment,
         "score": score, "max_score": 100,
         "submitted_at": (datetime.now() - timedelta(days=random.randint(1, 60))).isoformat()}
        for assignment, score in [
            ("Midterm Exam", random.randint(60, 100)),
            ("Final Exam", random.randint(55, 100)),
            ("Homework 1", random.randint(70, 100)),
            ("Homework 2", random.randint(65, 100)),
            ("Lab Report 1", random.randint(75, 100)),
            ("Research Paper", random.randint(60, 100)),
            ("Group Project", random.randint(70, 100)),
            ("Quiz 1", random.randint(50, 100)),
            ("Quiz 2", random.randint(55, 100)),
            ("Presentation", random.randint(70, 100)),
        ]
    ]

    return c


def _seed_ecommerce() -> dict[str, list[dict[str, Any]]]:
    """E-commerce domain seed data."""
    c: dict[str, list[dict[str, Any]]] = {}

    c["customers"] = [
        {"id": f"cust_{i:04d}", "name": name,
         "email": f"{name.lower().replace(' ', '.')}@example.com",
         "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
         "address": f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Elm', 'Cedar'])} St",
         "membership_tier": random.choice(["standard", "silver", "gold", "platinum"]),
         "created_at": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
         "status": random.choice(["active", "active", "active", "inactive"])}
        for i, name in enumerate([
            "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
            "Eva Martinez", "Frank Garcia", "Grace Lee", "Henry Wilson",
            "Iris Taylor", "Jack Anderson", "Kate Thomas", "Leo Jackson",
            "Mia White", "Noah Harris", "Olivia Martin", "Peter Thompson",
        ])
    ]

    c["products"] = [
        {"id": f"prod_{i:04d}", "name": name, "price": price, "category": cat,
         "sku": f"SKU-{random.randint(10000, 99999)}", "stock": random.randint(0, 500),
         "weight_kg": weight, "status": "active"}
        for i, (name, price, cat, weight) in enumerate([
            ("Wireless Bluetooth Headphones", 79.99, "electronics", 0.3),
            ("Organic Cotton T-Shirt", 29.99, "clothing", 0.2),
            ("Stainless Steel Water Bottle", 24.99, "home & kitchen", 0.4),
            ("Running Shoes Pro", 129.99, "footwear", 0.8),
            ("Laptop Backpack", 59.99, "accessories", 1.2),
            ("Ceramic Coffee Mug Set", 34.99, "home & kitchen", 1.5),
            ("Yoga Mat Premium", 44.99, "fitness", 2.0),
            ("Smartphone Case", 19.99, "electronics", 0.1),
            ("Bamboo Cutting Board", 27.99, "home & kitchen", 1.0),
            ("LED Desk Lamp", 49.99, "electronics", 1.8),
        ])
    ]

    c["orders"] = [
        {"id": f"ord_{uuid.uuid4().hex[:8]}",
         "customer_id": f"cust_{random.randint(0, 15):04d}",
         "items": [{"product_id": f"prod_{random.randint(0, 9):04d}", "quantity": random.randint(1, 3)}],
         "total": round(random.uniform(19.99, 299.99), 2),
         "status": random.choice(["pending", "processing", "shipped", "delivered", "returned"]),
         "shipping_address": f"{random.randint(100, 9999)} Elm St",
         "created_at": (datetime.now() - timedelta(days=random.randint(1, 90))).isoformat()}
        for _ in range(12)
    ]

    c["inventory"] = [
        {"id": f"inv_{i:04d}", "product_id": f"prod_{i:04d}",
         "warehouse": random.choice(["Warehouse A", "Warehouse B", "Warehouse C"]),
         "quantity": random.randint(10, 500),
         "reorder_point": random.randint(10, 50),
         "last_restocked": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat()}
        for i in range(10)
    ]

    c["shipping"] = [
        {"id": f"shp_{uuid.uuid4().hex[:8]}",
         "order_id": f"ord_{uuid.uuid4().hex[:8]}",
         "carrier": random.choice(["USPS", "FedEx", "UPS", "DHL"]),
         "tracking_number": f"TRK{random.randint(1000000000, 9999999999)}",
         "status": random.choice(["label_created", "in_transit", "out_for_delivery", "delivered"]),
         "estimated_delivery": (datetime.now() + timedelta(days=random.randint(1, 10))).strftime("%Y-%m-%d")}
        for _ in range(8)
    ]

    return c


def _seed_saas_support() -> dict[str, list[dict[str, Any]]]:
    """SaaS support domain seed data."""
    c: dict[str, list[dict[str, Any]]] = {}

    c["customers"] = [
        {"id": f"cust_{i:04d}", "name": name,
         "email": f"{name.lower().replace(' ', '.')}@example.com",
         "company": random.choice(["Acme Corp", "Globex Inc", "Initech", "Umbrella LLC", "Stark Industries"]),
         "plan": random.choice(["free", "starter", "pro", "enterprise"]),
         "mrr": round(random.uniform(0, 999.99), 2),
         "created_at": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
         "status": random.choice(["active", "active", "active", "churned"])}
        for i, name in enumerate([
            "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
            "Eva Martinez", "Frank Garcia", "Grace Lee", "Henry Wilson",
            "Iris Taylor", "Jack Anderson", "Kate Thomas", "Leo Jackson",
            "Mia White", "Noah Harris", "Olivia Martin", "Peter Thompson",
        ])
    ]

    c["tickets"] = [
        {"id": f"ticket_{i:04d}",
         "customer_id": f"cust_{random.randint(0, 15):04d}",
         "subject": subject,
         "category": cat,
         "priority": random.choice(["low", "medium", "high", "urgent"]),
         "status": random.choice(["open", "in_progress", "resolved", "closed"]),
         "created_at": (datetime.now() - timedelta(hours=random.randint(1, 168))).isoformat()}
        for i, (subject, cat) in enumerate([
            ("Can't login to dashboard", "authentication"),
            ("Billing question about Pro plan", "billing"),
            ("Feature request: export to CSV", "feature_request"),
            ("API rate limit exceeded", "api"),
            ("Integration with Slack not working", "integration"),
            ("Need to upgrade subscription", "billing"),
            ("SSO configuration failing", "authentication"),
            ("Webhook delivery delays", "api"),
        ])
    ]

    c["appointments"] = [
        {"id": f"apt_{uuid.uuid4().hex[:8]}",
         "customer_id": f"cust_{random.randint(0, 15):04d}",
         "date": (datetime.now() + timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d"),
         "time": f"{random.randint(9, 17):02d}:{random.choice(['00', '30'])}",
         "type": random.choice(["demo", "onboarding", "support", "quarterly_review"]),
         "status": "scheduled"}
        for _ in range(8)
    ]

    c["products"] = [
        {"id": f"prod_{i:04d}", "name": name, "price": price,
         "category": cat, "stock": random.randint(0, 500), "status": "active"}
        for i, (name, price, cat) in enumerate([
            ("Starter Plan Monthly", 19.99, "subscription"),
            ("Pro Plan Monthly", 49.99, "subscription"),
            ("Enterprise Annual", 499.99, "subscription"),
            ("API Access Add-on", 29.99, "add-on"),
            ("Priority Support", 99.99, "service"),
            ("Custom Integration", 199.99, "service"),
        ])
    ]

    c["orders"] = [
        {"id": f"ord_{uuid.uuid4().hex[:8]}",
         "customer_id": f"cust_{random.randint(0, 15):04d}",
         "product_id": f"prod_{random.randint(0, 5):04d}",
         "total": round(random.uniform(19.99, 499.99), 2),
         "status": random.choice(["pending", "completed", "refunded"]),
         "created_at": (datetime.now() - timedelta(days=random.randint(1, 90))).isoformat()}
        for _ in range(12)
    ]

    return c


def _seed_real_estate() -> dict[str, list[dict[str, Any]]]:
    """Real estate domain seed data."""
    c: dict[str, list[dict[str, Any]]] = {}

    c["properties"] = [
        {"id": f"prop_{i:04d}", "address": addr, "city": city,
         "type": ptype, "bedrooms": beds, "bathrooms": baths,
         "sqft": sqft, "price": price,
         "status": random.choice(["available", "under_contract", "sold"]),
         "agent_id": f"agt_{random.randint(0, 5):04d}",
         "listed_at": (datetime.now() - timedelta(days=random.randint(1, 120))).isoformat()}
        for i, (addr, city, ptype, beds, baths, sqft, price) in enumerate([
            ("123 Oak Avenue", "Springfield", "single_family", 3, 2, 1800, 349000),
            ("456 Maple Drive", "Riverside", "single_family", 4, 3, 2400, 525000),
            ("789 Pine Street, Unit 4B", "Downtown", "condo", 2, 1, 950, 275000),
            ("321 Cedar Lane", "Lakewood", "townhouse", 3, 2, 1600, 410000),
            ("555 Birch Boulevard", "Hillcrest", "single_family", 5, 4, 3200, 875000),
            ("100 Elm Court, Apt 12", "Midtown", "apartment", 1, 1, 650, 189000),
            ("200 Walnut Way", "Suburbia", "single_family", 4, 2, 2100, 465000),
            ("88 Willow Park", "Eastside", "townhouse", 2, 2, 1200, 315000),
            ("400 Spruce Heights", "Westend", "single_family", 3, 2, 1950, 395000),
            ("900 Magnolia Place", "Northgate", "condo", 2, 2, 1100, 299000),
        ])
    ]

    c["clients"] = [
        {"id": f"cli_{i:04d}", "name": name,
         "email": f"{name.lower().replace(' ', '.')}@example.com",
         "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
         "type": random.choice(["buyer", "seller", "both"]),
         "budget": random.randint(200000, 900000) if random.random() > 0.3 else None,
         "status": random.choice(["active", "active", "active", "closed"])}
        for i, name in enumerate([
            "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
            "Eva Martinez", "Frank Garcia", "Grace Lee", "Henry Wilson",
            "Iris Taylor", "Jack Anderson", "Kate Thomas", "Leo Jackson",
            "Mia White", "Noah Harris", "Olivia Martin", "Peter Thompson",
        ])
    ]

    c["agents"] = [
        {"id": f"agt_{i:04d}", "name": name,
         "license_number": f"RE-{random.randint(100000, 999999)}",
         "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
         "email": f"{name.lower().split()[-1]}@realty.com",
         "specialization": spec, "status": "active"}
        for i, (name, spec) in enumerate([
            ("Sarah Mitchell", "residential"),
            ("James Rodriguez", "commercial"),
            ("Emily Chen", "luxury"),
            ("Michael Brooks", "first-time buyers"),
            ("Diana Kowalski", "investment properties"),
            ("Anthony Russo", "rentals"),
        ])
    ]

    c["viewings"] = [
        {"id": f"viw_{uuid.uuid4().hex[:8]}",
         "property_id": f"prop_{random.randint(0, 9):04d}",
         "client_id": f"cli_{random.randint(0, 15):04d}",
         "agent_id": f"agt_{random.randint(0, 5):04d}",
         "date": (datetime.now() + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
         "time": f"{random.randint(10, 17):02d}:{random.choice(['00', '30'])}",
         "status": random.choice(["scheduled", "completed", "cancelled"]),
         "feedback": random.choice(["Loved the kitchen", "Too small", "Great location", "Needs renovation", None])}
        for _ in range(8)
    ]

    c["offers"] = [
        {"id": f"ofr_{uuid.uuid4().hex[:8]}",
         "property_id": f"prop_{random.randint(0, 9):04d}",
         "client_id": f"cli_{random.randint(0, 15):04d}",
         "amount": random.randint(180000, 900000),
         "status": random.choice(["pending", "accepted", "rejected", "countered"]),
         "contingencies": random.sample(["inspection", "financing", "appraisal", "sale_of_home"], k=random.randint(1, 3)),
         "expiry_date": (datetime.now() + timedelta(days=random.randint(3, 14))).strftime("%Y-%m-%d")}
        for _ in range(8)
    ]

    return c


def _seed_legal() -> dict[str, list[dict[str, Any]]]:
    """Legal domain seed data."""
    c: dict[str, list[dict[str, Any]]] = {}

    c["cases"] = [
        {"id": f"case_{i:04d}", "title": title,
         "case_number": f"CV-2025-{random.randint(1000, 9999)}",
         "type": ctype, "client_id": f"cli_{random.randint(0, 15):04d}",
         "attorney_id": f"att_{random.randint(0, 5):04d}",
         "status": random.choice(["open", "discovery", "trial", "settled", "closed"]),
         "filed_date": (datetime.now() - timedelta(days=random.randint(30, 365))).strftime("%Y-%m-%d")}
        for i, (title, ctype) in enumerate([
            ("Smith v. Acme Corp", "personal_injury"),
            ("Estate of Williams", "probate"),
            ("Johnson Divorce", "family"),
            ("Globex Patent Dispute", "intellectual_property"),
            ("Brown Employment Claim", "employment"),
            ("Garcia Contract Breach", "contract"),
            ("Lee Immigration Petition", "immigration"),
            ("Taylor Property Dispute", "real_estate"),
        ])
    ]

    c["clients"] = [
        {"id": f"cli_{i:04d}", "name": name,
         "email": f"{name.lower().replace(' ', '.')}@example.com",
         "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
         "type": random.choice(["individual", "individual", "corporate"]),
         "representation": random.choice(["plaintiff", "defendant", "petitioner"]),
         "status": random.choice(["active", "active", "active", "closed"])}
        for i, name in enumerate([
            "Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
            "Eva Martinez", "Frank Garcia", "Grace Lee", "Henry Wilson",
            "Iris Taylor", "Jack Anderson", "Kate Thomas", "Leo Jackson",
            "Mia White", "Noah Harris", "Olivia Martin", "Peter Thompson",
        ])
    ]

    c["attorneys"] = [
        {"id": f"att_{i:04d}", "name": name,
         "bar_number": f"BAR-{random.randint(100000, 999999)}",
         "email": f"{name.lower().split()[-1]}@lawfirm.com",
         "specialization": spec,
         "hourly_rate": rate, "status": "active"}
        for i, (name, spec, rate) in enumerate([
            ("Margaret Sullivan", "personal injury", 350),
            ("Richard Yamamoto", "corporate law", 450),
            ("Patricia Okonkwo", "family law", 300),
            ("Andrew Petrov", "intellectual property", 500),
            ("Christine DeLuca", "employment law", 375),
            ("Samuel Wright", "criminal defense", 400),
        ])
    ]

    c["documents"] = [
        {"id": f"doc_{uuid.uuid4().hex[:8]}",
         "case_id": f"case_{random.randint(0, 7):04d}",
         "title": title, "type": dtype,
         "filed_date": (datetime.now() - timedelta(days=random.randint(1, 180))).strftime("%Y-%m-%d"),
         "status": random.choice(["draft", "filed", "served", "accepted"]),
         "file_path": f"/documents/{dtype}/{uuid.uuid4().hex[:8]}.pdf"}
        for title, dtype in [
            ("Initial Complaint", "complaint"),
            ("Motion to Dismiss", "motion"),
            ("Discovery Request", "discovery"),
            ("Witness Deposition", "deposition"),
            ("Settlement Agreement", "agreement"),
            ("Expert Report", "report"),
            ("Court Brief", "brief"),
            ("Evidence Exhibit A", "exhibit"),
            ("Subpoena - Records", "subpoena"),
            ("Closing Arguments", "brief"),
        ]
    ]

    c["court_dates"] = [
        {"id": f"crt_{uuid.uuid4().hex[:8]}",
         "case_id": f"case_{random.randint(0, 7):04d}",
         "date": (datetime.now() + timedelta(days=random.randint(7, 90))).strftime("%Y-%m-%d"),
         "time": f"{random.randint(9, 15):02d}:{random.choice(['00', '30'])}",
         "courtroom": f"Room {random.randint(100, 500)}",
         "judge": random.choice(["Hon. R. Patterson", "Hon. M. Alvarez", "Hon. S. Kim", "Hon. T. Williams"]),
         "type": random.choice(["hearing", "trial", "arraignment", "sentencing", "mediation"]),
         "status": random.choice(["scheduled", "confirmed", "postponed"])}
        for _ in range(8)
    ]

    return c


_DOMAIN_SEED_FACTORIES: dict[str, Any] = {
    "default": _seed_default,
    "healthcare": _seed_healthcare,
    "education": _seed_education,
    "ecommerce": _seed_ecommerce,
    "saas_support": _seed_saas_support,
    "real_estate": _seed_real_estate,
    "legal": _seed_legal,
}

# Domain-specific keyword → collection routing for tool-name detection
_DOMAIN_COLLECTION_MAP: dict[str, dict[str, str]] = {
    "healthcare": {
        "patient": "patients", "doctor": "doctors", "physician": "doctors",
        "appointment": "appointments", "schedule": "appointments", "checkup": "appointments",
        "record": "medical_records", "diagnosis": "medical_records", "prescription": "medical_records",
    },
    "education": {
        "student": "students", "pupil": "students",
        "course": "courses", "class": "courses", "subject": "courses",
        "enrollment": "enrollments", "enroll": "enrollments", "register": "enrollments",
        "grade": "grades", "score": "grades", "mark": "grades",
        "teacher": "teachers", "instructor": "teachers", "professor": "teachers",
    },
    "ecommerce": {
        "customer": "customers", "shopper": "customers", "buyer": "customers",
        "product": "products", "item": "products", "merchandise": "products",
        "order": "orders", "purchase": "orders", "transaction": "orders",
        "inventory": "inventory", "stock": "inventory", "warehouse": "inventory",
        "shipping": "shipping", "shipment": "shipping", "delivery": "shipping", "track": "shipping",
    },
    "saas_support": {
        "customer": "customers", "user": "customers", "subscriber": "customers",
        "ticket": "tickets", "issue": "tickets", "support": "tickets",
        "appointment": "appointments", "meeting": "appointments", "demo": "appointments",
        "product": "products", "plan": "products", "subscription": "products",
        "order": "orders",
    },
    "real_estate": {
        "property": "properties", "listing": "properties", "house": "properties", "home": "properties",
        "client": "clients", "buyer": "clients", "seller": "clients",
        "viewing": "viewings", "showing": "viewings", "tour": "viewings", "visit": "viewings",
        "agent": "agents", "realtor": "agents", "broker": "agents",
        "offer": "offers", "bid": "offers", "proposal": "offers",
    },
    "legal": {
        "case": "cases", "matter": "cases", "litigation": "cases",
        "client": "clients", "party": "clients",
        "document": "documents", "filing": "documents", "brief": "documents", "contract": "documents",
        "court": "court_dates", "hearing": "court_dates", "trial": "court_dates",
        "attorney": "attorneys", "lawyer": "attorneys", "counsel": "attorneys",
    },
}


class MockDataStore:
    """In-memory data store with seed data for common business domains.

    Parameters
    ----------
    domain : str | None
        Business domain key (e.g. ``"healthcare"``, ``"legal"``).
        When *None* (the default), the ``"default"`` generic seed data is used,
        preserving full backward compatibility.
    """

    def __init__(self, domain: str | None = None) -> None:
        self.domain = domain or "default"
        self._collections: dict[str, list[dict[str, Any]]] = {}
        self._seed_data_loaded = False

    def _ensure_seed_data(self) -> None:
        if self._seed_data_loaded:
            return
        self._seed_data_loaded = True
        factory = _DOMAIN_SEED_FACTORIES.get(self.domain, _seed_default)
        self._collections = factory()

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


# ---------------------------------------------------------------------------
# Global store registry — one MockDataStore per domain, created on demand
# ---------------------------------------------------------------------------

_domain_stores: dict[str, MockDataStore] = {}


def _get_store(domain: str = "default") -> MockDataStore:
    """Return (and lazily create) the MockDataStore for *domain*."""
    if domain not in _domain_stores:
        _domain_stores[domain] = MockDataStore(domain)
    return _domain_stores[domain]


# Backward-compatible global store for callers that import ``_store`` directly
_store = _get_store("default")


def create_mock_tool_function(
    tool_name: str,
    description: str,
    parameters: list[dict],
    domain: str | None = None,
) -> Any:
    """
    Create a functional mock tool function based on the tool's name and parameters.

    Detects the tool's intent from its name and maps to appropriate mock backend
    operations.  When *domain* is provided the store and collection routing are
    tailored to that domain (e.g. ``"healthcare"`` routes ``"patient"`` keywords
    to the ``patients`` collection with medical seed data).

    Returns a real async function that returns realistic mock data.
    """
    store = _get_store(domain or "default")
    name_lower = tool_name.lower()
    effective_domain = domain or "default"

    # --- Resolve collection via domain-specific keyword map (if available) ---
    collection: str | None = None
    cmap = _DOMAIN_COLLECTION_MAP.get(effective_domain, {})
    for keyword, coll in cmap.items():
        if keyword in name_lower:
            collection = coll
            break

    # --- Determine operation type ---
    operation = "query"  # default
    if any(w in name_lower for w in ["create", "schedule", "book", "submit", "open", "add", "enroll", "register", "file"]):
        operation = "create"
    elif any(w in name_lower for w in ["cancel", "delete", "remove"]):
        operation = "delete"
    elif any(w in name_lower for w in ["update", "modify", "change", "reschedule"]):
        operation = "update"

    # --- Fallback: generic collection detection (original logic) ---
    if collection is None:
        if any(w in name_lower for w in ["schedule", "book", "appointment", "meeting"]):
            collection = "appointments"
        elif any(w in name_lower for w in ["ticket", "issue", "support", "case"]):
            collection = "tickets"
        elif any(w in name_lower for w in ["customer", "user", "client", "contact"]):
            collection = "customers"
        elif any(w in name_lower for w in ["order", "purchase", "transaction"]):
            collection = "orders"
        elif any(w in name_lower for w in ["product", "item", "inventory"]):
            collection = "products"
        else:
            # Last resort: pick first available collection in the store
            store._ensure_seed_data()
            collection = next(iter(store._collections), "customers")

    async def mock_tool_fn(**kwargs: Any) -> str:
        """Mock tool that returns realistic data from the mock data store."""
        try:
            if operation == "query":
                filters = {k: v for k, v in kwargs.items() if v and k != "limit"}
                results = store.query(collection, filters if filters else None)
                limit = int(kwargs.get("limit", 10))
                results = results[:limit]
                return json.dumps({
                    "success": True,
                    "collection": collection,
                    "count": len(results),
                    "results": results,
                }, indent=2, default=str)

            elif operation == "create":
                record = store.create(collection, kwargs)
                return json.dumps({
                    "success": True,
                    "message": f"Created new {collection[:-1] if collection.endswith('s') else collection}",
                    "record": record,
                }, indent=2, default=str)

            elif operation == "update":
                item_id = kwargs.pop("id", kwargs.pop("item_id", kwargs.pop(f"{collection[:-1]}_id", "")))
                if item_id:
                    record = store.update(collection, item_id, kwargs)
                    if record:
                        return json.dumps({"success": True, "updated": record}, indent=2, default=str)
                return json.dumps({"success": False, "error": "Item not found"})

            elif operation == "delete":
                item_id = kwargs.get("id", kwargs.get("item_id", ""))
                deleted = store.delete(collection, item_id)
                return json.dumps({"success": deleted, "message": "Deleted" if deleted else "Not found"})

            else:
                return json.dumps({"success": True, "data": kwargs, "mock": True})

        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    return mock_tool_fn
