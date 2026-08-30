from unittest.mock import Mock, patch

from app.services.pdf_text_values import extract_textual_total


def _reader_with_text(text: str):
    page = Mock()
    page.extract_text.return_value = text
    reader = Mock()
    reader.pages = [page]
    return reader


def test_extracts_labeled_total_without_confusing_other_figures():
    text = """RUC: 20613452436
PRECIO: S/ 40,338.98
Subtotal: S/ 40,338.98
IGV: S/ 7,261.02
Total: S/ 47,600.00
Plazo de Entrega: 15 dias
"""
    with patch("app.services.pdf_text_values.PdfReader", return_value=_reader_with_text(text)):
        assert extract_textual_total(b"%PDF") == "47600.00"


def test_does_not_treat_subtotal_or_ruc_as_total():
    text = "RUC: 20613452436\nSubtotal: S/ 40,338.98\nIGV: S/ 7,261.02"
    with patch("app.services.pdf_text_values.PdfReader", return_value=_reader_with_text(text)):
        assert extract_textual_total(b"%PDF") is None


def test_supports_decimal_comma_on_exact_total_line():
    with patch(
        "app.services.pdf_text_values.PdfReader",
        return_value=_reader_with_text("TOTAL DEL CONTRATO: S/ 47600,00"),
    ):
        assert extract_textual_total(b"%PDF") == "47600.00"


def test_uses_schedule_reference_when_pdf_contains_multiple_total_lines():
    text = "Total: S/ 2,006.00\nTotal: S/ 47,600.00\nTotal: S/ 0.00"
    with patch("app.services.pdf_text_values.PdfReader", return_value=_reader_with_text(text)):
        assert extract_textual_total(b"%PDF", expected_total=47600.00) == "47600.00"


def test_does_not_guess_between_multiple_totals_without_reference():
    text = "Total: S/ 2,006.00\nTotal: S/ 47,600.00"
    with patch("app.services.pdf_text_values.PdfReader", return_value=_reader_with_text(text)):
        assert extract_textual_total(b"%PDF") is None
