"""Normalisation and matching helpers for comparing land records.

Everything here is deterministic and explainable (no AI):
- survey numbers: digits normalised to 0-9, spaces removed, upper-cased
- names / places: exact match, spelling similarity (difflib), or a simple
  consonant "phonetic key" that lets Devanagari (Hindi / Marathi) text be
  compared with its English spelling, e.g. "सुरेश कुमार" ~ "Suresh Kumar".
  Other Indian scripts are not covered by the phonetic key yet.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from .extraction import normalize_digits

HONORIFICS = {
    "shri", "sri", "shree", "smt", "shrimati", "mr", "mrs", "ms", "dr", "late", "sh",
    "श्री", "श्रीमती", "स्व", "स्वर्गीय", "कु", "डॉ",
}

# Devanagari consonant -> phonetic key letter (aspirated/unaspirated and sibilants merged)
DEVANAGARI = {
    "क": "k", "ख": "k", "ग": "g", "घ": "g", "ङ": "n",
    "च": "c", "छ": "c", "ज": "j", "झ": "j", "ञ": "n",
    "ट": "t", "ठ": "t", "ड": "d", "ढ": "d", "ण": "n",
    "त": "t", "थ": "t", "द": "d", "ध": "d", "न": "n", "ऩ": "n",
    "प": "p", "फ": "p", "ब": "b", "भ": "b", "म": "m",
    "य": "y", "र": "r", "ऱ": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "s", "ष": "s", "स": "s", "ह": "h",
    "ं": "n", "ँ": "n",  # anusvara / chandrabindu
    "क़": "k", "ख़": "k", "ग़": "g", "ज़": "j", "ड़": "d", "ढ़": "d", "फ़": "p", "य़": "y",
}

# Latin spelling -> the same key letters. Order matters (longer patterns first).
# "ch" becomes a temporary upper-case "C" so the later plain "c" -> "k" rule (Lucknow) skips it.
LATIN_RULES = [
    ("chh", "C"), ("ch", "C"), ("ksh", "ks"), ("ngh", "nh"), ("sh", "s"), ("th", "t"), ("dh", "d"),
    ("bh", "b"), ("kh", "k"), ("gh", "g"), ("ph", "p"), ("jh", "j"), ("ck", "k"),
    ("x", "ks"), ("q", "k"), ("z", "j"), ("f", "p"), ("w", "v"), ("c", "k"),
]


def is_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def is_latin(text: str) -> bool:
    return any(ch.isascii() and ch.isalpha() for ch in text)


def normalize_survey(value: str | None) -> str | None:
    if not value:
        return None
    key = re.sub(r"\s+", "", normalize_digits(value)).upper()
    return key or None


def _strip_honorifics(words: list[str]) -> list[str]:
    return [w for w in words if w.strip(".").lower() not in HONORIFICS]


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFC", value).lower()
    value = re.sub(r"[^\w\sऀ-෿]", " ", value)
    return " ".join(_strip_honorifics(value.split()))


def phonetic_key(value: str | None, drop_semivowels: bool = False) -> str | None:
    """Consonant skeleton of a Latin or Devanagari string, or None for other scripts."""
    text = normalize_text(value)
    if not text:
        return None
    words = []
    for word in text.split():
        if is_devanagari(word):
            word = unicodedata.normalize("NFC", word)
            # ड़ / ढ़ are flapped "r" sounds and usually romanised with "r" (Kheri = खेड़ी).
            word = word.replace("ड़", "र").replace("ढ़", "र").replace("़", "")
            chars = [DEVANAGARI.get(ch, "") for ch in word]
            key = "".join(chars)
        elif word.isascii():
            for src, dst in LATIN_RULES:
                word = word.replace(src, dst)
            key = re.sub(r"[^a-z]", "", re.sub(r"[aeiou]", "", word).lower())
        else:
            return None
        if drop_semivowels:
            key = re.sub(r"[yvh]", "", key)
        key = re.sub(r"(.)\1+", r"\1", key)
        if key:
            words.append(key)
    return " ".join(words) or None


def names_match(a: str | None, b: str | None) -> tuple[bool, str | None]:
    """Return (match, method) for two person names."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False, None
    if na == nb:
        return True, "exact"
    if is_latin(na) and is_latin(nb) and not is_devanagari(na + nb):
        if SequenceMatcher(None, na, nb).ratio() >= 0.85:
            return True, "spelling variant"
    if is_devanagari(na) and is_devanagari(nb) and SequenceMatcher(None, na, nb).ratio() >= 0.85:
        return True, "spelling variant"
    # The phonetic key is loose (only consonants), so it is used only across scripts.
    if is_devanagari(na) != is_devanagari(nb):
        ka, kb = phonetic_key(na), phonetic_key(nb)
        if ka and kb and ka == kb:
            return True, "cross-script"
    return False, None


def places_match(a: str | None, b: str | None) -> tuple[bool, str | None]:
    """Village / district comparison. Phonetic matching only across scripts
    (so 'Rampur' and 'Rampura' stay different, but 'रामपुर' ~ 'Rampur')."""
    na, nb = normalize_text(a).replace(" ", ""), normalize_text(b).replace(" ", "")
    if not na or not nb:
        return False, None
    if na == nb:
        return True, "exact"
    if is_devanagari(na) != is_devanagari(nb):
        ka, kb = phonetic_key(a, drop_semivowels=True), phonetic_key(b, drop_semivowels=True)
        if ka and kb and ka.replace(" ", "") == kb.replace(" ", ""):
            return True, "cross-script"
    return False, None


# Approximate conversion to hectares. Bigha differs by state, so it is only
# compared with other Bigha values.
TO_HECTARE = {
    "Hectare": 1.0,
    "Acre": 0.404686,
    "Sq. Metre": 0.0001,
    "Kanal": 0.0505857,
    "Guntha": 0.0101171,
}
AREA_TOLERANCE = 0.05  # 5 %


def compare_areas(a_value, a_unit, b_value, b_unit) -> dict | None:
    """Return details if the two areas differ by more than the tolerance, else None."""
    if not a_value or not b_value or not a_unit or not b_unit:
        return None
    if a_unit == b_unit:
        x, y, unit = float(a_value), float(b_value), a_unit
    elif a_unit in TO_HECTARE and b_unit in TO_HECTARE:
        x, y, unit = float(a_value) * TO_HECTARE[a_unit], float(b_value) * TO_HECTARE[b_unit], "Hectare"
    else:
        return None  # e.g. Bigha vs Acre: regional unit, not compared
    if max(x, y) == 0:
        return None
    diff = abs(x - y) / max(x, y)
    if diff <= AREA_TOLERANCE:
        return None
    return {"a": round(x, 4), "b": round(y, 4), "unit": unit, "difference_pct": round(diff * 100, 1)}
