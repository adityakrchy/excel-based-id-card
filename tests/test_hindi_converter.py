"""Unit tests for Hindi font detection and Kruti Dev / DevLys to Unicode conversion."""

import pytest
from id_card_generator.data.hindi_converter import HindiConverter


def test_is_unicode_devanagari():
    assert HindiConverter.is_unicode_devanagari("श्री अंकित कुमार") is True
    assert HindiConverter.is_unicode_devanagari("जाले") is True
    assert HindiConverter.is_unicode_devanagari("Hello World") is False
    assert HindiConverter.is_unicode_devanagari("12345") is False
    assert HindiConverter.is_unicode_devanagari("") is False


def test_is_krutidev_font():
    assert HindiConverter.is_krutidev_font("Kruti Dev 010") is True
    assert HindiConverter.is_krutidev_font("krutidev 020") is True
    assert HindiConverter.is_krutidev_font("DevLys 010") is True
    assert HindiConverter.is_krutidev_font("devlys") is True
    assert HindiConverter.is_krutidev_font("Chanakya") is True
    assert HindiConverter.is_krutidev_font("Arial") is False
    assert HindiConverter.is_krutidev_font("Mangal") is False
    assert HindiConverter.is_krutidev_font(None) is False


def test_detect_krutidev_text():
    # Names with Shree / Kumar
    assert HindiConverter.detect_krutidev_text("Jh vafdr dqekj") is True
    assert HindiConverter.detect_krutidev_text("Jh fiUVq") is True
    assert HindiConverter.detect_krutidev_text("Jh vfouk'k dqekj feJ") is True
    assert HindiConverter.detect_krutidev_text("eks0 unhe") is True
    assert HindiConverter.detect_krutidev_text("tkys") is True
    assert HindiConverter.detect_krutidev_text("24&iz[kaM fodkl") is True
    assert HindiConverter.detect_krutidev_text("Øe") is True

    # Standard English words and numbers should not be falsely detected
    assert HindiConverter.detect_krutidev_text("SL.NO") is False
    assert HindiConverter.detect_krutidev_text("NAME") is False
    assert HindiConverter.detect_krutidev_text("MOBILE") is False
    assert HindiConverter.detect_krutidev_text("VIDEOGRAPHER") is False
    assert HindiConverter.detect_krutidev_text("6299109865") is False
    assert HindiConverter.detect_krutidev_text("John Doe") is False

    # Already Unicode Devanagari should not be detected as Kruti Dev
    assert HindiConverter.detect_krutidev_text("श्री अंकित कुमार") is False


def test_kruti_to_unicode_names():
    assert HindiConverter.kruti_to_unicode("Jh vafdr dqekj") == "श्री अंकित कुमार"
    assert HindiConverter.kruti_to_unicode("Jh fiUVq") == "श्री पिन्टु"
    assert HindiConverter.kruti_to_unicode("Jh vfouk'k dqekj feJ") == "श्री अविनाश कुमार मिश्र"
    assert HindiConverter.kruti_to_unicode("Jh fodkl dqekj") == "श्री विकास कुमार"
    assert HindiConverter.kruti_to_unicode("Jh fgeka'kq dqekj") == "श्री हिमांशु कुमार"
    assert HindiConverter.kruti_to_unicode("Jh lUuh dqekj") == "श्री सन्नी कुमार"
    assert HindiConverter.kruti_to_unicode("Jh f'koe dqekj") == "श्री शिवम कुमार"
    assert HindiConverter.kruti_to_unicode("Jh Kku jke eaMy") == "श्री ज्ञान राम मंडल"


def test_kruti_to_unicode_places_and_offices():
    assert HindiConverter.kruti_to_unicode("tkys") == "जाले"
    assert HindiConverter.kruti_to_unicode("flagokM+k") == "सिंहवाड़ा"
    assert HindiConverter.kruti_to_unicode("dsoVh") == "केवटी"
    assert HindiConverter.kruti_to_unicode("lnj njHkaxk") == "सदर दरभंगा"
    assert HindiConverter.kruti_to_unicode("uxj fuxe") == "नगर निगम"


def test_kruti_to_unicode_headers():
    assert HindiConverter.kruti_to_unicode("Øe") == "क्रम"
    assert HindiConverter.kruti_to_unicode("iz[kaM dk uke") == "प्रखंड का नाम"
    assert HindiConverter.kruti_to_unicode("vH;qfDr") == "अभ्युक्ति"
    assert HindiConverter.kruti_to_unicode("la[;k") == "संख्या"
    assert HindiConverter.kruti_to_unicode("ohfM;ksxzkQj dk uke") == "वीडियोग्राफर का नाम"
    assert HindiConverter.kruti_to_unicode("eksckbZy la[;k") == "मोबाईल संख्या"


def test_kruti_to_unicode_preserves_unicode_and_numbers():
    # Devanagari (Mangal) unchanged
    assert HindiConverter.kruti_to_unicode("श्री अंकित कुमार") == "श्री अंकित कुमार"
    # Pure numbers unchanged
    assert HindiConverter.kruti_to_unicode("9876543210") == "9876543210"
    assert HindiConverter.kruti_to_unicode("") == ""


def test_convert_value_modes():
    val = "Jh vafdr dqekj"
    # Auto mode detects Kruti
    assert HindiConverter.convert_value(val, font_name="Arial", mode="auto") == "श्री अंकित कुमार"
    # Auto mode with explicit font name
    assert HindiConverter.convert_value(val, font_name="Kruti Dev 010", mode="auto") == "श्री अंकित कुमार"
    # Force mode
    assert HindiConverter.convert_value(val, font_name=None, mode="kruti_to_unicode") == "श्री अंकित कुमार"
    # None mode preserves raw
    assert HindiConverter.convert_value(val, font_name="Kruti Dev 010", mode="none") == "Jh vafdr dqekj"

    # English value preserved in auto mode
    assert HindiConverter.convert_value("VIDEOGRAPHER", font_name="Arial", mode="auto") == "VIDEOGRAPHER"
