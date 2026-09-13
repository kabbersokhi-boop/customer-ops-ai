CATALOG = {
    "Fortuner": [
        ("4x2 AT", "Diesel", "Automatic", 3_890_000),
        ("4x4 AT", "Diesel", "Automatic", 4_350_000),
    ],
    "Legender": [("4x2 AT", "Diesel", "Automatic", 4_400_000)],
    "Camry": [("Hybrid", "Hybrid", "e-CVT", 4_850_000)],
    "Innova Hycross": [("VX Hybrid", "Hybrid", "e-CVT", 3_000_000), ("GX", "Petrol", "CVT", 2_250_000)],
    "Innova Crysta": [("GX", "Diesel", "Manual", 2_150_000)],
    "Urban Cruiser Hyryder": [
        ("V Hybrid", "Hybrid", "e-CVT", 1_950_000),
        ("G NeoDrive", "Petrol", "Automatic", 1_750_000),
    ],
    "Glanza": [("V AMT", "Petrol", "Automatic", 1_050_000)],
    "Taisor": [("V Turbo AT", "Petrol", "Automatic", 1_350_000)],
    "Rumion": [("V AT", "Petrol", "Automatic", 1_350_000)],
    "Hilux": [("High AT", "Diesel", "Automatic", 3_900_000)],
}

COLOURS = [
    "Super White",
    "Pearl White",
    "Attitude Black",
    "Silver Metallic",
    "Grey Metallic",
    "Red",
    "Blue",
    "Bronze",
]

BRANCHES = ["Gurugram", "New Delhi", "Noida", "Faridabad", "Ghaziabad"]
UNITS_PER_MODEL = 30
EXPECTED_DELIVERY_DAYS = [0, 3, 5, 7, 10, 14, 21]
INVENTORY_STATES = ["AVAILABLE", "RESERVED"]

SEED_BASELINE = {
    "inventory": len(CATALOG) * UNITS_PER_MODEL,
    "customers": 60,
    "leads": 60,
    "interactions": 60,
    "appointments": 16,
    "pending_approvals": 5,
    "service_requests": 12,
}

NOT_INCLUDED = [
    "real manufacturer or dealer inventory, prices, customers, or service history",
    "real WhatsApp traffic or production telephony",
    "a production dealer-management-system integration",
    "approved warranty, policy, or product-specification retrieval",
    "live lender rates or finance approvals",
    "arbitrary vehicle models outside the bounded catalogue",
]


def demo_world_definition() -> dict:
    return {
        "synthetic": True,
        "statement": "The data is synthetic; the workflow, policy, failure, and integration behavior is real.",
        "catalogue": {
            "inventory_rows": SEED_BASELINE["inventory"],
            "models": [
                {
                    "name": model,
                    "seeded_units": UNITS_PER_MODEL,
                    "variants": [variant for variant, _, _, _ in variants],
                }
                for model, variants in CATALOG.items()
            ],
            "branches": BRANCHES,
            "colours": COLOURS,
            "inventory_states": INVENTORY_STATES,
            "expected_delivery_days": EXPECTED_DELIVERY_DAYS,
            "attributes": [
                "stock ID",
                "model",
                "variant",
                "fuel type",
                "transmission",
                "colour",
                "branch",
                "synthetic demo price",
                "availability state",
                "test-drive flag",
                "expected-delivery days",
            ],
        },
        "operational_seed": SEED_BASELINE,
        "not_included": NOT_INCLUDED,
    }
