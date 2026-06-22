import re
import unicodedata

from .neighborhood_catalog import NEIGHBORHOODS


def normalize_text(s: str):
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _score_alias_match(text: str, alias: str, *, title_mode: bool = False) -> int:
    if not text or not alias:
        return 0

    normalized_text = normalize_text(text)
    alias = normalize_text(alias).strip()

    if not alias:
        return 0

    alias_pattern = rf"\b{re.escape(alias)}\b"

    if not re.search(alias_pattern, normalized_text):
        return 0

    direct_patterns = [
        rf"\b(?:zona|cartier(?:ul|ului)?|in|din)\s+{re.escape(alias)}\b",
        rf"\bzona\s+cartier(?:ul|ului)?\s+{re.escape(alias)}\b",
        rf"\b(?:situat(?:a)?|localizat(?:a)?|amplasat(?:a)?|pozitionat(?:a)?)\s+(?:in|din|pe)\s+{re.escape(alias)}\b",
        rf"\b(?:in\s+zona|din\s+zona)\s+{re.escape(alias)}\b",
    ]

    nearby_patterns = [
        rf"\b(?:langa|aproape\s+de|in\s+apropiere(?:a)?\s+de|vis-a-vis\s+de)\s+{re.escape(alias)}\b",
        rf"\b(?:langa\s+zona|aproape\s+de\s+zona|in\s+apropierea\s+zonei)\s+{re.escape(alias)}\b",
        rf"\b(?:acces\s+rapid\s+spre|acces\s+facil\s+catre)\s+{re.escape(alias)}\b",
    ]

    if any(re.search(pattern, normalized_text) for pattern in direct_patterns):
        return 150 if title_mode else 90

    if any(re.search(pattern, normalized_text) for pattern in nearby_patterns):
        return 20 if title_mode else 10

    return 110 if title_mode else 35


def build_alias_index():
    alias_index = []

    for canonical, config in NEIGHBORHOODS.items():
        city = config["city"]

        for alias in config["aliases"]:
            alias_index.append({
                "canonical": canonical,
                "city": city,
                "alias": normalize_text(alias).strip(),
            })

    alias_index.sort(key=lambda item: len(item["alias"]), reverse=True)
    return alias_index


ALIAS_INDEX = build_alias_index()


def _extract_nearby_neighborhood(text: str, excluded: str = None):
    if not text:
        return None

    normalized_text = normalize_text(text)
    matches = []

    for entry in ALIAS_INDEX:
        canonical = entry["canonical"]
        alias = entry["alias"]

        if canonical == excluded:
            continue

        nearby_patterns = [
            rf"\b(?:langa|aproape\s+de|in\s+apropiere(?:a)?\s+de|vis-a-vis\s+de)\s+{re.escape(alias)}\b",
            rf"\b(?:langa\s+zona|aproape\s+de\s+zona|in\s+apropierea\s+zonei)\s+{re.escape(alias)}\b",
            rf"\b(?:acces\s+rapid\s+spre|acces\s+facil\s+catre)\s+{re.escape(alias)}\b",
        ]

        if any(re.search(pattern, normalized_text) for pattern in nearby_patterns):
            matches.append((len(alias), canonical))

    if not matches:
        return None

    matches.sort(reverse=True)
    return matches[0][1]


def _score_to_confidence(score: int) -> str:
    if score >= 140:
        return "high"
    if score >= 70:
        return "medium"
    return "low"


def resolve_location(title: str, text: str):
    combined_text = normalize_text(f"{title or ''}\n{text or ''}")

    if "city of mara" in combined_text:
        return {
            "neighborhood": "Circumvalatiunii",
            "city": "Timisoara",
            "nearby_neighborhood": None,
            "location_confidence": "high",
        }

    candidates = []

    for canonical, config in NEIGHBORHOODS.items():
        best_score = 0
        best_alias_length = 0

        for alias in config["aliases"]:
            normalized_alias = normalize_text(alias).strip()

            title_score = _score_alias_match(title, normalized_alias, title_mode=True)
            text_score = _score_alias_match(text, normalized_alias, title_mode=False)

            total_score = title_score + text_score
            alias_length = len(normalized_alias)

            if total_score > best_score or (
                total_score == best_score and alias_length > best_alias_length
            ):
                best_score = total_score
                best_alias_length = alias_length

        if best_score > 0:
            candidates.append({
                "neighborhood": canonical,
                "city": config["city"],
                "score": best_score,
                "alias_length": best_alias_length,
            })

    if not candidates:
        return {
            "neighborhood": None,
            "city": None,
            "nearby_neighborhood": None,
            "location_confidence": "low",
        }

    candidates.sort(
        key=lambda item: (item["score"], item["alias_length"]),
        reverse=True
    )

    best = candidates[0]
    nearby_neighborhood = _extract_nearby_neighborhood(
        text,
        excluded=best["neighborhood"]
    )

    return {
        "neighborhood": best["neighborhood"],
        "city": best["city"],
        "nearby_neighborhood": nearby_neighborhood,
        "location_confidence": _score_to_confidence(best["score"]),
    }
