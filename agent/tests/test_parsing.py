from agent.parsing import detect_product_lines

from shared import ProductLine


def test_detect_lines_english_and_taglish() -> None:
    assert detect_product_lines("insurance for my dog and an upcoming trip") == [
        ProductLine.TRAVEL,
        ProductLine.PET,
    ]
    assert ProductLine.PET in detect_product_lines("para sa aso ko")
    assert detect_product_lines("hello") == []
