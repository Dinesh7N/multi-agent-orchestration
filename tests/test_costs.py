from decimal import Decimal

from debate.costs import ModelPricing


def test_model_pricing_calculate_cost() -> None:
    pricing = ModelPricing(input_per_million=Decimal("2.00"), output_per_million=Decimal("4.00"))
    cost = pricing.calculate_cost(1000, 2000)
    assert cost == Decimal("0.010")
