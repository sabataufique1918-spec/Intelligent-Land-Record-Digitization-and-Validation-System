"""Pattern-based field suggestions from OCR text.

Looks for common English / Hindi / Marathi labels (e.g. "Khasra No.", "ग्राम",
"District") and takes the text that follows them on the same line. This is
simple keyword matching, NOT AI / NER extraction, so every suggestion must be
checked by the user before it is saved.
"""

import re
import unicodedata

# Non-ASCII labels are listed without word boundaries; ASCII ones get letter boundaries.
LABELS: dict[str, list[str]] = {
    "owner_name": [
        r"buyer'?s?\s*name", r"buyer", r"vendee", r"purchaser", "क्रेता(?:\\s*का\\s*नाम)?",
        r"owner'?s?\s*name", r"name\s*of\s*(?:the\s*)?(?:land\s*)?owner", r"owner", r"khatedar'?s?\s*name",
        r"khatedar", r"holder'?s?\s*name", "खातेदार\\s*का\\s*नाम", "खातेदार", "भूस्वामी\\s*का\\s*नाम", "भूस्वामी",
        "भूमिधर\\s*का\\s*नाम", "भूमिधर", "मालिक\\s*का\\s*नाम", "मालिक", "धारक\\s*का\\s*नाम", "खातेदाराचे\\s*नाव",
    ],
    "father_name": [
        r"father'?s?\s*/\s*husband'?s?\s*name", r"father'?s?\s*name", r"husband'?s?\s*name", r"s/o", r"d/o", r"w/o",
        "पिता\\s*/\\s*पति\\s*का\\s*नाम", "पिता\\s*का\\s*नाम", "पति\\s*का\\s*नाम", "पिता", "वडिलांचे\\s*नाव",
    ],
    "previous_owner": [
        r"seller'?s?\s*name", r"seller", r"vendor", r"transferor", r"executant", r"previous\s*owner",
        "विक्रेता(?:\\s*का\\s*नाम)?", "पूर्व\\s*स्वामी", "हस्तांतरणकर्ता",
    ],
    "document_date": [
        r"date\s*of\s*registration", r"registration\s*date", r"date\s*of\s*execution", r"dated", r"date",
        "पंजीकरण\\s*तिथि", "दिनांक", "तारीख", "तिथि",
    ],
    "survey_number": [
        r"survey\s*(?:no|number)\.?", r"sy\.?\s*no\.?", r"khasra\s*(?:no|number)\.?", r"plot\s*(?:no|number)\.?",
        r"gat\s*(?:no|number)\.?", r"dag\s*(?:no|number)\.?",
        "खसरा\\s*(?:नं|संख्या|क्रमांक|नम्बर|नंबर)?\\.?", "सर्वे\\s*(?:नं|क्रमांक|नंबर)?\\.?",
        "सर्व्हे\\s*(?:नं|क्रमांक)?\\.?", "गट\\s*(?:नं|क्रमांक)?\\.?",
    ],
    "khata_number": [
        r"khata\s*(?:no|number)\.?", r"khatauni\s*(?:no|number)\.?", r"khewat\s*(?:no|number)\.?",
        r"account\s*(?:no|number)\.?",
        "खाता\\s*(?:नं|संख्या|क्रमांक|नम्बर|नंबर)?\\.?", "खतौनी\\s*(?:नं|संख्या)?\\.?", "खेवट\\s*(?:नं|संख्या)?\\.?",
    ],
    "village": [r"village", r"mauza", r"mouza", "ग्राम", "गांव", "गाँव", "मौजा", "गाव"],
    "tehsil": [r"tehsil", r"tahsil", r"taluka", r"taluk", r"mandal", "तहसील", "तालुका"],
    "district": [r"district", r"dist\.", "जनपद", "ज़िला", "जिला", "जिल्हा"],
    "state": [r"state", "राज्य"],
    "area": [r"total\s*area", r"area", "कुल\\s*रकबा", "रकबा", "क्षेत्रफल", "क्षेत्र"],
}

UNITS = [
    (r"hectares?|hect\.?|ha\b|हेक्टेयर|हे\.|हेक्टर", "Hectare"),
    (r"acres?|एकड़|एकड|एकर", "Acre"),
    (r"bighas?|बीघा", "Bigha"),
    (r"kanals?|कनाल", "Kanal"),
    (r"gunthas?|guntas?|गुंठा|गुंठे", "Guntha"),
    (r"sq\.?\s*m(?:etres?|eters?)?|square\s*met(?:re|er)s?|वर्ग\s*मीटर", "Sq. Metre"),
]

SURVEY_TOKEN = re.compile(r"\d+[A-Za-z]?(?:\s*/\s*\d+[A-Za-z]?)*")
NUMBER_TOKEN = re.compile(r"\d+(?:\.\d+)?")
LEADING_JUNK = re.compile(r"^[\s:：\-–—=|.,)(]+")
TRAILING_JUNK = re.compile(r"[\s:：,;|\-–—=(]+$")


INDIC = "ऀ-෿"  # Devanagari ... Sinhala blocks (letters and vowel signs)


def _compile(pattern: str) -> str:
    if pattern.isascii():
        return rf"(?<![A-Za-z]){pattern}(?![A-Za-z])"
    # Stop e.g. "गाव" (village) matching inside the name "वडगाव".
    return rf"(?<![{INDIC}\w]){pattern}(?![{INDIC}])"


_LABEL_RE = [
    (field, re.compile(_compile(p), re.IGNORECASE))
    for field, patterns in LABELS.items()
    for p in patterns
]


def normalize_digits(text: str) -> str:
    """Convert Devanagari, Tamil, Bengali, etc. digits to 0-9."""
    return "".join(
        str(unicodedata.digit(ch)) if ch.isdigit() and not ch.isascii() else ch for ch in text
    )


def _label_spans(line: str) -> list[tuple[int, int, str]]:
    found = [(m.start(), m.end(), field) for field, rx in _LABEL_RE for m in rx.finditer(line)]
    found.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    accepted: list[tuple[int, int, str]] = []
    for span in found:
        if accepted and span[0] < accepted[-1][1]:
            continue  # overlaps a longer / earlier label
        accepted.append(span)
    return accepted


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_date(text: str) -> str | None:
    """Find a date (Indian day-first order) in text and return it as YYYY-MM-DD."""
    from datetime import date

    text = normalize_digits(text or "")
    candidates = []
    m = re.search(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", text)
    if m:
        candidates.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    m = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)", text)
    if m:
        candidates.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    m = re.search(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", text)
    if m and m.group(2).lower() in MONTHS:
        candidates.append((int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))))
    for y, mo, d in candidates:
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            continue
    return None


def _clean_value(field: str, raw: str) -> dict | None:
    value = TRAILING_JUNK.sub("", LEADING_JUNK.sub("", re.split(r"\s{3,}|\|", raw.strip())[0]))
    if not value:
        return None
    if field == "survey_number" or field == "khata_number":
        m = SURVEY_TOKEN.search(value)
        return {"value": re.sub(r"\s+", "", m.group())} if m else None
    if field == "document_date":
        iso = parse_date(value)
        return {"value": iso} if iso else None
    if field == "area":
        m = NUMBER_TOKEN.search(value)
        if not m:
            return None
        result = {"value": m.group()}
        for pattern, unit in UNITS:
            if re.search(pattern, value[m.end():], re.IGNORECASE):
                result["unit"] = unit
                break
        return result
    if not re.search(r"[^\W\d_]", value):  # must contain letters
        return None
    return {"value": value[:120]}


def _collapse_repeated_marks(text: str) -> str:
    """Some PDF text layers repeat vowel signs (e.g. 'ग्रााम'); keep one of each run."""
    out = []
    for ch in text:
        if out and ch == out[-1] and unicodedata.category(ch).startswith("M"):
            continue
        out.append(ch)
    return "".join(out)


def suggest_fields(text: str | None) -> dict[str, dict]:
    if not text:
        return {}
    suggestions: dict[str, dict] = {}
    lines = [line for line in _collapse_repeated_marks(normalize_digits(text)).splitlines() if line.strip()]
    for index, line in enumerate(lines):
        spans = _label_spans(line)
        for i, (start, end, field) in enumerate(spans):
            if field in suggestions or (field == "area" and "area_value" in suggestions):
                continue
            last = i + 1 == len(spans)
            stop = len(line) if last else spans[i + 1][0]
            source = line.strip()
            method = "label_same_line"
            cleaned = _clean_value(field, line[end:stop])
            # Table layouts often put the value on the next line (label cell, then value cell).
            if not cleaned and last and index + 1 < len(lines) and not _label_spans(lines[index + 1]):
                cleaned = _clean_value(field, lines[index + 1])
                source = f"{line.strip()} → {lines[index + 1].strip()}"
                method = "label_next_line"
            if not cleaned:
                continue
            label = line[start:end].strip()
            if field == "area":
                suggestions["area_value"] = {"value": cleaned["value"], "source": source, "method": method, "label": label}
                if cleaned.get("unit"):
                    suggestions["area_unit"] = {"value": cleaned["unit"], "source": source, "method": method, "label": label}
            else:
                suggestions[field] = {"value": cleaned["value"], "source": source, "method": method, "label": label}
    return suggestions
