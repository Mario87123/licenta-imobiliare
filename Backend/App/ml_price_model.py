import json
import math
import os
import random
from datetime import datetime
from pathlib import Path

from .database import get_connection


MODEL_DIR = Path(os.getenv("ML_MODEL_DIR", Path(__file__).resolve().parent / "ml_models"))
MODEL_PATH = MODEL_DIR / "price_knn_model.json"

MIN_PRICE = 10000
MAX_PRICE = 2000000
MIN_SURFACE = 10
MAX_SURFACE = 500
DEFAULT_K = 12

NUMERIC_FEATURES = {
    "surface_mp": 0.34,
    "rooms": 0.18,
    "floor": 0.08,
    "total_floors": 0.05,
    "year_built": 0.12,
}

CATEGORICAL_FEATURES = {
    "neighborhood": 0.46,
    "city": 0.12,
    "partitioning": 0.05,
    "source": 0.03,
    "location_confidence": 0.02,
}


def _to_float(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _clean_text(value):
    return (value or "").strip().lower()


def _median(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return None

    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]

    return (values[mid - 1] + values[mid]) / 2


def _percentile(values, percentile):
    values = sorted(value for value in values if value is not None)
    if not values:
        return None

    if len(values) == 1:
        return values[0]

    position = (len(values) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _fetch_training_rows():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            id,
            price_eur,
            surface_mp,
            rooms,
            neighborhood,
            city,
            floor,
            total_floors,
            year_built,
            partitioning,
            source,
            location_confidence
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND price_eur IS NOT NULL
          AND surface_mp IS NOT NULL
          AND surface_mp > 0
          AND rooms IS NOT NULL
          AND neighborhood IS NOT NULL
          AND price_eur BETWEEN ? AND ?
          AND surface_mp BETWEEN ? AND ?
          AND (
              duplicate_group_id IS NULL
              OR canonical_ad_id IS NULL
              OR canonical_ad_id = id
          )
    """, (MIN_PRICE, MAX_PRICE, MIN_SURFACE, MAX_SURFACE))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def _build_defaults(rows):
    defaults = {}
    ranges = {}

    for feature in NUMERIC_FEATURES:
        values = [_to_float(row.get(feature)) for row in rows]
        values = [value for value in values if value is not None]
        default = _median(values) if values else 0
        min_value = min(values) if values else 0
        max_value = max(values) if values else 1

        defaults[feature] = default
        ranges[feature] = max(max_value - min_value, 1)

    for feature in CATEGORICAL_FEATURES:
        counts = {}
        for row in rows:
            value = _clean_text(row.get(feature))
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1

        defaults[feature] = max(counts, key=counts.get) if counts else ""

    return defaults, ranges


def _prepare_sample(row, defaults):
    surface = _to_float(row.get("surface_mp"))
    price = _to_float(row.get("price_eur"))

    if not surface or not price:
        return None

    features = {}

    for feature in NUMERIC_FEATURES:
        value = _to_float(row.get(feature))
        features[feature] = value if value is not None else defaults.get(feature, 0)

    for feature in CATEGORICAL_FEATURES:
        value = _clean_text(row.get(feature))
        features[feature] = value or defaults.get(feature, "")

    return {
        "id": row.get("id"),
        "features": features,
        "price_eur": price,
        "surface_mp": surface,
        "price_per_mp": price / surface,
    }


def _distance(features_a, features_b, ranges):
    total = 0

    for feature, weight in NUMERIC_FEATURES.items():
        value_a = _to_float(features_a.get(feature)) or 0
        value_b = _to_float(features_b.get(feature)) or 0
        total += weight * abs(value_a - value_b) / ranges.get(feature, 1)

    for feature, weight in CATEGORICAL_FEATURES.items():
        value_a = _clean_text(features_a.get(feature))
        value_b = _clean_text(features_b.get(feature))
        if not value_a or not value_b:
            total += weight * 0.5
        elif value_a != value_b:
            total += weight

    return total


def _predict_from_samples(target_features, samples, ranges, k=DEFAULT_K, exclude_id=None):
    scored = []

    for sample in samples:
        if exclude_id is not None and sample.get("id") == exclude_id:
            continue

        dist = _distance(target_features, sample["features"], ranges)
        weight = 1 / ((dist + 0.03) ** 2)
        scored.append((dist, weight, sample))

    scored.sort(key=lambda item: item[0])
    nearest = scored[:k]

    if not nearest:
        return None

    total_weight = sum(weight for _, weight, _ in nearest)
    estimated_price_per_mp = (
        sum(sample["price_per_mp"] * weight for _, weight, sample in nearest)
        / total_weight
    )

    nearest_price_per_mp = [sample["price_per_mp"] for _, _, sample in nearest]
    avg_distance = sum(dist for dist, _, _ in nearest) / len(nearest)

    return {
        "estimated_price_per_mp": estimated_price_per_mp,
        "low_price_per_mp": _percentile(nearest_price_per_mp, 0.20) or estimated_price_per_mp,
        "high_price_per_mp": _percentile(nearest_price_per_mp, 0.80) or estimated_price_per_mp,
        "avg_distance": avg_distance,
        "neighbors": [
            {
                "id": sample["id"],
                "distance": round(dist, 4),
                "price_eur": round(sample["price_eur"]),
                "surface_mp": sample["surface_mp"],
                "price_per_mp": round(sample["price_per_mp"], 2),
            }
            for dist, _, sample in nearest
        ],
    }


def _evaluate_model(samples, ranges):
    if len(samples) < 30:
        return {
            "mae": None,
            "mape": None,
            "rmse": None,
            "test_samples": 0,
        }

    rng = random.Random(42)
    shuffled = samples[:]
    rng.shuffle(shuffled)

    test_size = max(10, int(len(shuffled) * 0.2))
    test_rows = shuffled[:test_size]
    train_rows = shuffled[test_size:]

    errors = []
    percentage_errors = []
    squared_errors = []

    for row in test_rows:
        prediction = _predict_from_samples(
            row["features"],
            train_rows,
            ranges,
            k=DEFAULT_K,
        )
        if not prediction:
            continue

        predicted_price = prediction["estimated_price_per_mp"] * row["surface_mp"]
        actual_price = row["price_eur"]
        error = abs(predicted_price - actual_price)

        errors.append(error)
        percentage_errors.append(error / actual_price)
        squared_errors.append(error ** 2)

    if not errors:
        return {
            "mae": None,
            "mape": None,
            "rmse": None,
            "test_samples": 0,
        }

    return {
        "mae": round(sum(errors) / len(errors), 2),
        "mape": round((sum(percentage_errors) / len(percentage_errors)) * 100, 2),
        "rmse": round(math.sqrt(sum(squared_errors) / len(squared_errors)), 2),
        "test_samples": len(errors),
    }


def train_ml_price_model(min_samples: int = 80):
    rows = _fetch_training_rows()

    if len(rows) < min_samples:
        return {
            "status": "not_enough_data",
            "message": f"Sunt necesare cel putin {min_samples} anunturi valide pentru modelul ML.",
            "training_samples": len(rows),
        }

    defaults, ranges = _build_defaults(rows)
    samples = []

    for row in rows:
        sample = _prepare_sample(row, defaults)
        if sample:
            samples.append(sample)

    if len(samples) < min_samples:
        return {
            "status": "not_enough_data",
            "message": f"Dupa curatare au ramas doar {len(samples)} anunturi valide.",
            "training_samples": len(samples),
        }

    metrics = _evaluate_model(samples, ranges)

    payload = {
        "model_type": "weighted_knn_regression",
        "target": "price_eur",
        "trained_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "training_samples": len(samples),
        "features": {
            "numeric": list(NUMERIC_FEATURES.keys()),
            "categorical": list(CATEGORICAL_FEATURES.keys()),
        },
        "weights": {
            "numeric": NUMERIC_FEATURES,
            "categorical": CATEGORICAL_FEATURES,
        },
        "defaults": defaults,
        "ranges": ranges,
        "metrics": metrics,
        "samples": samples,
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    return {
        "status": "trained",
        "model_type": payload["model_type"],
        "trained_at": payload["trained_at"],
        "training_samples": len(samples),
        "metrics": metrics,
    }


def load_ml_price_model():
    if not MODEL_PATH.exists():
        return None

    try:
        return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_ml_model_status():
    model = load_ml_price_model()

    if not model:
        return {
            "is_trained": False,
            "message": "Modelul ML nu este antrenat inca.",
        }

    return {
        "is_trained": True,
        "model_type": model.get("model_type"),
        "trained_at": model.get("trained_at"),
        "training_samples": model.get("training_samples"),
        "metrics": model.get("metrics"),
    }


def predict_ml_price(target):
    model = load_ml_price_model()

    if not model:
        return {
            "error": "Modelul ML nu este antrenat inca.",
        }

    surface = _to_float(target.get("surface_mp"))
    rooms = _to_int(target.get("rooms"))

    if not surface or surface < MIN_SURFACE or surface > MAX_SURFACE:
        return {
            "error": "Suprafata trebuie sa fie intre 10 si 500 mp.",
        }

    if not rooms or rooms < 1 or rooms > 10:
        return {
            "error": "Numarul de camere trebuie sa fie intre 1 si 10.",
        }

    defaults = model["defaults"]
    ranges = model["ranges"]

    target_row = {
        **target,
        "surface_mp": surface,
        "rooms": rooms,
        "city": target.get("city") or "Timisoara",
    }
    target_sample = _prepare_sample(
        {
            **target_row,
            "price_eur": surface * 1,
        },
        defaults,
    )

    prediction = _predict_from_samples(
        target_sample["features"],
        model["samples"],
        ranges,
        k=DEFAULT_K,
    )

    if not prediction:
        return {
            "error": "Nu exista suficiente vecini ML pentru estimare.",
        }

    estimated_price = round(prediction["estimated_price_per_mp"] * surface)
    low_estimate = round(prediction["low_price_per_mp"] * surface * 0.97)
    high_estimate = round(prediction["high_price_per_mp"] * surface * 1.03)

    metrics = model.get("metrics") or {}
    mape = metrics.get("mape")

    if mape is not None:
        low_estimate = min(low_estimate, round(estimated_price * (1 - min(mape, 25) / 100)))
        high_estimate = max(high_estimate, round(estimated_price * (1 + min(mape, 25) / 100)))

    avg_distance = prediction["avg_distance"]
    training_samples = model.get("training_samples", 0)

    if training_samples >= 500 and avg_distance <= 0.08:
        confidence = "high"
    elif training_samples >= 150 and avg_distance <= 0.16:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "input": target_row,
        "estimate": {
            "estimated_price": estimated_price,
            "low_estimate": low_estimate,
            "high_estimate": high_estimate,
            "estimated_price_per_mp": round(prediction["estimated_price_per_mp"], 2),
            "confidence": confidence,
            "method": model.get("model_type"),
            "neighbors_used": len(prediction["neighbors"]),
            "avg_neighbor_distance": round(avg_distance, 4),
        },
        "model": {
            "trained_at": model.get("trained_at"),
            "training_samples": training_samples,
            "metrics": metrics,
        },
        "neighbors": prediction["neighbors"],
    }
