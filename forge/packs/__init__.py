"""Pre-built domain packs — instant agency blueprints without LLM calls."""

from forge.packs.saas_support import create_saas_support_blueprint
from forge.packs.ecommerce import create_ecommerce_blueprint
from forge.packs.real_estate import create_real_estate_blueprint

AVAILABLE_PACKS = {
    "saas_support": {
        "name": "SaaS Customer Support",
        "description": "AI-powered support, onboarding, and retention for SaaS products",
        "create": create_saas_support_blueprint,
    },
    "ecommerce": {
        "name": "E-Commerce Operations",
        "description": "Order management, customer service, marketing, and analytics for online stores",
        "create": create_ecommerce_blueprint,
    },
    "real_estate": {
        "name": "Real Estate Agency",
        "description": "Lead generation, property matching, scheduling, and client management",
        "create": create_real_estate_blueprint,
    },
}

def list_packs() -> dict:
    return {k: v["description"] for k, v in AVAILABLE_PACKS.items()}

def create_from_pack(pack_name: str) -> "AgencyBlueprint":
    if pack_name not in AVAILABLE_PACKS:
        raise ValueError(f"Unknown pack '{pack_name}'. Available: {list(AVAILABLE_PACKS.keys())}")
    return AVAILABLE_PACKS[pack_name]["create"]()
