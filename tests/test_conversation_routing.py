import pytest

from app.services.conversation import assess_message


@pytest.mark.parametrize(
    "message",
    [
        "car trouble breakage",
        "my car has a problem",
        "vehicle issue, something is not working",
        "my Innova Crysta is broken",
        "the car stopped working",
        "engine trouble",
        "there is a leak under the vehicle",
        "my steering is acting up",
        "flat tyre on my car",
        "the vehicle is shaking and making a rattling noise",
    ],
)
def test_natural_vehicle_trouble_routes_to_service(message: str):
    assessment = assess_message(message, has_supported_model="innova crysta" in message.lower())
    assert assessment.intent == "service"
    assert assessment.request_type == "service_request"


@pytest.mark.parametrize(
    "message",
    [
        "I want to buy a car but I have an issue deciding which one",
        "I have a problem choosing between a new car and an SUV",
        "I want to purchase an Innova Hycross but I have an issue with my budget",
    ],
)
def test_generic_problem_language_does_not_override_clear_purchase_intent(message: str):
    assessment = assess_message(message, has_supported_model="innova hycross" in message.lower())
    assert assessment.intent == "sales"
    assert assessment.request_type in {"sales_discovery", "inventory_enquiry"}


def test_service_package_stays_policy_question_not_vehicle_repair():
    assessment = assess_message("What is included in the service package?", has_supported_model=False)
    assert assessment.intent == "sales"
    assert assessment.request_type == "unverified_policy_question"


def test_explicit_repair_language_wins_even_if_purchase_words_are_present():
    assessment = assess_message(
        "I was going to buy another car, but my current vehicle has brake trouble and needs repair",
        has_supported_model=False,
    )
    assert assessment.intent == "service"
    assert assessment.request_type == "service_request"
