import re
from dataclasses import dataclass

UNSUPPORTED_BRANDS = {
    "audi": "Audi",
    "bmw": "BMW",
    "ford": "Ford",
    "honda": "Honda",
    "hyundai": "Hyundai",
    "kia": "Kia",
    "mahindra": "Mahindra",
    "maruti": "Maruti Suzuki",
    "mercedes": "Mercedes-Benz",
    "mg": "MG",
    "skoda": "Skoda",
    "tata": "Tata",
    "volkswagen": "Volkswagen",
}

SERVICE_STRONG_TERMS = [
    "service",
    "servicing",
    "repair",
    "brake",
    "brakes",
    "braking",
    "oil change",
    "maintenance",
    "workshop",
    "warning light",
    "check engine",
    "engine light",
    "breakdown",
    "broke down",
    "broken down",
    "stranded",
    "won't start",
    "wont start",
    "will not start",
    "not starting",
    "overheat",
    "overheating",
    "smoke",
    "fire",
    "puncture",
    "flat tyre",
    "flat tire",
    "battery dead",
    "dead battery",
    "rattling",
    "rattle",
    "grinding",
    "squealing",
    "vibration",
    "shaking",
    "leak",
    "leaking",
    "awaaz",
]

GENERIC_VEHICLE_CONCERNS = [
    "problem",
    "issue",
    "trouble",
    "broken",
    "breakage",
    "damage",
    "damaged",
    "fault",
    "faulty",
    "malfunction",
    "not working",
    "stopped working",
    "doesn't work",
    "doesnt work",
    "acting up",
]

VEHICLE_CONCERN_ANCHORS = [
    "car",
    "vehicle",
    "engine",
    "gearbox",
    "transmission",
    "steering",
    "wheel",
    "tyre",
    "tire",
    "battery",
    "ac",
    "air conditioning",
    "clutch",
    "suspension",
    "dashboard",
    "door",
    "window",
]

CLEAR_PURCHASE_TERMS = [
    "buy",
    "purchase",
    "budget",
    "lakh",
    "test drive",
    "showroom",
    "exchange",
    "trade-in",
    "trade in",
    "new car",
    "new vehicle",
]


@dataclass(frozen=True)
class MessageAssessment:
    intent: str
    request_type: str
    human_requested: bool = False
    untrusted_instruction_detected: bool = False
    unsupported_vehicle: str | None = None
    requested_discount_inr: int | None = None


def _contains_phrase(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _extract_discount(message: str) -> int | None:
    low = message.lower()
    if "discount" not in low and "off" not in low:
        return None

    word_lakhs = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }
    words = re.search(r"\b(one|two|three|four|five)\s+(?:lakh|lac)\b", low)
    if words:
        return word_lakhs[words.group(1)] * 100_000

    lakhs = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|lakhs|lacs)\b", low)
    if lakhs:
        return int(float(lakhs.group(1)) * 100_000)

    rupees = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+)", low)
    if rupees:
        return int(rupees.group(1).replace(",", ""))
    return None


def _unsupported_vehicle(message: str, has_supported_model: bool) -> str | None:
    if has_supported_model:
        return None
    low = message.lower()
    for token, display_name in UNSUPPORTED_BRANDS.items():
        if re.search(rf"\b{re.escape(token)}\b", low):
            return display_name
    return None


def _looks_like_service_concern(text: str, *, has_supported_model: bool) -> bool:
    if _contains_phrase(text, SERVICE_STRONG_TERMS):
        return True

    if not _contains_phrase(text, GENERIC_VEHICLE_CONCERNS):
        return False

    has_vehicle_anchor = has_supported_model or _contains_phrase(text, VEHICLE_CONCERN_ANCHORS)
    if not has_vehicle_anchor:
        return False

    # A generic word such as "issue" should not turn an explicit purchase request into a service case.
    # Concrete repair/safety language above still wins when a customer mentions both contexts.
    return not _contains_phrase(text, CLEAR_PURCHASE_TERMS)


def assess_message(message: str, *, has_supported_model: bool) -> MessageAssessment:
    low = " ".join(message.lower().split())
    human_requested = _contains_phrase(
        low,
        ["human", "real person", "salesperson", "sales person", "agent please", "talk to someone"],
    )
    injection = _contains_phrase(
        low,
        [
            "ignore your previous",
            "ignore previous",
            "ignore your rules",
            "system administrator",
            "reveal your instructions",
            "reveal system prompt",
            "you are now the system",
        ],
    )

    if human_requested:
        return MessageAssessment(
            intent="support",
            request_type="human_handoff",
            human_requested=True,
            untrusted_instruction_detected=injection,
        )

    # "Service package" is a policy question, not a request to service a vehicle.
    if _contains_phrase(low, ["warranty", "guarantee", "service package"]):
        return MessageAssessment(
            intent="sales",
            request_type="unverified_policy_question",
            untrusted_instruction_detected=injection,
        )

    if _looks_like_service_concern(low, has_supported_model=has_supported_model):
        return MessageAssessment(
            intent="service",
            request_type="service_request",
            untrusted_instruction_detected=injection,
        )

    if "roadside assistance" in low:
        return MessageAssessment(
            intent="sales",
            request_type="unverified_policy_question",
            untrusted_instruction_detected=injection,
        )

    requested_discount = _extract_discount(message)
    if requested_discount is not None or "discount" in low:
        return MessageAssessment(
            intent="sales",
            request_type="discount_request",
            requested_discount_inr=requested_discount,
            untrusted_instruction_detected=injection,
        )

    unsupported_vehicle = _unsupported_vehicle(message, has_supported_model)
    if unsupported_vehicle:
        return MessageAssessment(
            intent="sales",
            request_type="unsupported_vehicle",
            unsupported_vehicle=unsupported_vehicle,
            untrusted_instruction_detected=injection,
        )

    if _contains_phrase(
        low,
        ["mileage", "fuel efficiency", "kmpl", "horsepower", "engine power", "ground clearance", "dimensions"],
    ):
        return MessageAssessment(
            intent="sales",
            request_type="unverified_specification_question",
            untrusted_instruction_detected=injection,
        )

    if _contains_phrase(low, ["finance rate", "financing rate", "interest rate", "loan rate", "emi rate"]):
        return MessageAssessment(
            intent="sales",
            request_type="unverified_finance_question",
            untrusted_instruction_detected=injection,
        )

    if _contains_phrase(low, ["book the same", "book it", "book twice", "create an appointment"]):
        return MessageAssessment(
            intent="sales",
            request_type="booking_request",
            untrusted_instruction_detected=injection,
        )

    greeting = low in {
        "hi",
        "hello",
        "hey",
        "hi there",
        "hello there",
        "namaste",
        "good morning",
        "good afternoon",
        "good evening",
    }
    if greeting:
        return MessageAssessment(
            intent="general",
            request_type="greeting",
            untrusted_instruction_detected=injection,
        )

    sales_terms = [
        "car",
        "vehicle",
        "suv",
        "buy",
        "purchase",
        "budget",
        "lakh",
        "test drive",
        "book",
        "appointment",
        "automatic",
        "manual",
        "showroom",
        "exchange",
        "trade-in",
        "trade in",
    ]
    if has_supported_model or _contains_phrase(low, sales_terms):
        request_type = "inventory_enquiry" if has_supported_model or "budget" in low or "lakh" in low else "sales_discovery"
        return MessageAssessment(
            intent="sales",
            request_type=request_type,
            untrusted_instruction_detected=injection,
        )

    return MessageAssessment(
        intent="general",
        request_type="unclear",
        untrusted_instruction_detected=injection,
    )
