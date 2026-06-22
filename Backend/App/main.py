import hashlib
import os
import secrets
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import init_db, get_connection
from .crawler_registry import get_crawler
from .duplicate_detector import (
    detect_duplicate_groups,
    get_duplicate_groups,
    get_rejected_duplicate_ads,
)
from .data_audit import get_data_quality_audit
from .neighborhood_catalog import NEIGHBORHOODS
from .price_estimator import estimate_price
from .ml_price_model import (
    get_ml_model_status,
    predict_ml_price,
    train_ml_price_model,
)


app = FastAPI(title="Licenta Imobiliare API")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=160)
    password: str = Field(..., min_length=6, max_length=128)


class EstimateRequest(BaseModel):
    neighborhood: str = Field(..., min_length=1, max_length=80)
    city: str = Field(default="Timisoara", max_length=80)
    surface_mp: float = Field(..., ge=10, le=500)
    rooms: int = Field(..., ge=1, le=10)
    floor: Optional[int] = Field(default=None, ge=-2, le=60)
    total_floors: Optional[int] = Field(default=None, ge=1, le=60)
    year_built: Optional[int] = Field(default=None, ge=1850, le=2035)
    partitioning: Optional[str] = Field(default=None, max_length=80)


SESSION_DAYS = 7
PASSWORD_RESET_MINUTES = 30


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return f"{salt}${digest}"


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split("$", 1)
    except ValueError:
        return False

    return secrets.compare_digest(hash_password(password, salt), stored_hash)


def public_user(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def require_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Autentificare necesara")

    token = authorization.split(" ", 1)[1].strip()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT users.*
        FROM user_sessions
        JOIN users ON users.id = user_sessions.user_id
        WHERE user_sessions.token = ?
          AND datetime(user_sessions.expires_at) > datetime('now')
    """, (token,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Sesiune invalida sau expirata")

    return dict(row)


def require_admin(current_user=Depends(require_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acces permis doar administratorului")

    return current_user


def format_sql_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def run_crawler_with_duplicate_detection(crawler, job_id, max_pages, max_ads, mode):
    crawler(job_id, max_pages, max_ads, mode)

    try:
        summary = detect_duplicate_groups()
        print(f"[DUPLICATES] Detectare finalizata dupa crawl: {summary}")
    except Exception as exc:
        print(f"[DUPLICATES] Eroare la detectare dupa crawl: {exc}")


def mark_interrupted_crawl_jobs():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE crawl_jobs
        SET status = ?,
            message = ?,
            finished_at = CURRENT_TIMESTAMP
        WHERE status IN ('pending', 'running', 'cancelling')
          AND finished_at IS NULL
    """, (
        "failed",
        "Job intrerupt deoarece backend-ul a fost repornit sau thread-ul crawlerului s-a oprit.",
    ))

    conn.commit()
    conn.close()


@app.on_event("startup")
def startup_event():
    init_db()
    mark_interrupted_crawl_jobs()


@app.get("/")
def root():
    return {"message": "API-ul merge"}


@app.post("/auth/register")
def register_user(payload: RegisterRequest):
    email = normalize_email(payload.email)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Exista deja un cont cu acest email")

    cursor.execute("""
        INSERT INTO users (name, email, password_hash, role)
        VALUES (?, ?, ?, ?)
    """, (
        payload.name.strip(),
        email,
        hash_password(payload.password),
        "user",
    ))
    user_id = cursor.lastrowid
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.commit()
    conn.close()

    return {"user": public_user(user)}


@app.post("/auth/login")
def login_user(payload: LoginRequest):
    email = normalize_email(payload.email)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user or not verify_password(payload.password, user["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Email sau parola invalida")

    token = secrets.token_urlsafe(32)
    expires_at = format_sql_datetime(datetime.utcnow() + timedelta(days=SESSION_DAYS))

    cursor.execute("""
        INSERT INTO user_sessions (user_id, token, expires_at)
        VALUES (?, ?, ?)
    """, (user["id"], token, expires_at))
    cursor.execute(
        "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user["id"],),
    )
    cursor.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    updated_user = cursor.fetchone()
    conn.commit()
    conn.close()

    return {"token": token, "user": public_user(updated_user)}


@app.post("/auth/password-reset/request")
def request_password_reset(payload: PasswordResetRequest):
    email = normalize_email(payload.email)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    cursor.execute("""
        DELETE FROM password_reset_tokens
        WHERE datetime(expires_at) <= datetime('now')
           OR used_at IS NOT NULL
    """)

    response = {
        "message": "Daca email-ul exista, a fost generat un cod de resetare.",
        "reset_token": None,
        "expires_in_minutes": PASSWORD_RESET_MINUTES,
    }

    if user:
        reset_token = secrets.token_urlsafe(24)
        expires_at = format_sql_datetime(
            datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_MINUTES)
        )

        cursor.execute("""
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (?, ?, ?)
        """, (
            user["id"],
            hash_reset_token(reset_token),
            expires_at,
        ))
        response["reset_token"] = reset_token

    conn.commit()
    conn.close()
    return response


@app.post("/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmRequest):
    token_hash = hash_reset_token(payload.token.strip())
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM password_reset_tokens
        WHERE token_hash = ?
          AND used_at IS NULL
          AND datetime(expires_at) > datetime('now')
    """, (token_hash,))
    reset_row = cursor.fetchone()

    if not reset_row:
        conn.close()
        raise HTTPException(status_code=400, detail="Cod de resetare invalid sau expirat")

    cursor.execute("""
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
    """, (
        hash_password(payload.password),
        reset_row["user_id"],
    ))
    cursor.execute("""
        UPDATE password_reset_tokens
        SET used_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (reset_row["id"],))
    cursor.execute(
        "DELETE FROM user_sessions WHERE user_id = ?",
        (reset_row["user_id"],),
    )

    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Parola a fost resetata cu succes."}


@app.get("/auth/me")
def read_current_user(current_user=Depends(require_user)):
    return {"user": public_user(current_user)}


@app.post("/auth/logout")
def logout_user(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()

    return {"status": "ok"}


def apply_ads_filters(
    query: str,
    params: list,
    neighborhood: Optional[str] = None,
    rooms: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_surface: Optional[float] = None,
    max_surface: Optional[float] = None,
    source: Optional[str] = None,
    city: Optional[str] = None,
    min_confidence: Optional[str] = None,
):
    if neighborhood:
        query += " AND neighborhood LIKE ?"
        params.append(f"%{neighborhood}%")

    if rooms is not None:
        query += " AND rooms = ?"
        params.append(rooms)

    if min_price is not None:
        query += " AND price_eur >= ?"
        params.append(min_price)

    if max_price is not None:
        query += " AND price_eur <= ?"
        params.append(max_price)

    if min_surface is not None:
        query += " AND surface_mp >= ?"
        params.append(min_surface)

    if max_surface is not None:
        query += " AND surface_mp <= ?"
        params.append(max_surface)

    if source:
        query += " AND source = ?"
        params.append(source)

    if city:
        query += " AND city = ?"
        params.append(city)

    if min_confidence == "high":
        query += " AND location_confidence = ?"
        params.append("high")
    elif min_confidence == "medium":
        query += " AND location_confidence IN (?, ?)"
        params.extend(["high", "medium"])
    elif min_confidence == "low":
        query += " AND location_confidence IN (?, ?, ?)"
        params.extend(["high", "medium", "low"])

    return query, params


DEFAULT_MAP_VIEW = {
    "Timisoara": {
        "center": [45.7590, 21.2197],
        "zoom": 12,
    },
    "Dumbravita": {
        "center": [45.8012, 21.2424],
        "zoom": 13,
    },
    "Giroc": {
        "center": [45.6948, 21.2358],
        "zoom": 13,
    },
    "Mosnita Noua": {
        "center": [45.7228, 21.3254],
        "zoom": 13,
    },
}


def get_map_view_for_city(city: Optional[str]):
    if city in DEFAULT_MAP_VIEW:
        return DEFAULT_MAP_VIEW[city]

    return DEFAULT_MAP_VIEW["Timisoara"]


def build_point_radius(count_ads: int) -> int:
    if count_ads <= 1:
        return 10
    if count_ads <= 3:
        return 14
    if count_ads <= 6:
        return 18
    if count_ads <= 10:
        return 22
    if count_ads <= 15:
        return 26
    return 30


@app.get("/ads")
def get_ads(
    neighborhood: Optional[str] = None,
    rooms: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_surface: Optional[float] = None,
    max_surface: Optional[float] = None,
    source: Optional[str] = None,
    city: Optional[str] = None,
    min_confidence: Optional[str] = None,
):
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM ads WHERE COALESCE(is_active, 1) = 1"
    params = []

    query, params = apply_ads_filters(
        query,
        params,
        neighborhood=neighborhood,
        rooms=rooms,
        min_price=min_price,
        max_price=max_price,
        min_surface=min_surface,
        max_surface=max_surface,
        source=source,
        city=city,
        min_confidence=min_confidence,
    )

    query += " ORDER BY created_at DESC, id DESC"

    cursor.execute(query, params)
    ads = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return ads


@app.post("/crawl/start")
def start_crawl(
    source: str = "olx",
    mode: str = "quick_refresh",
    max_pages: Optional[int] = None,
    max_ads: Optional[int] = None,
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO crawl_jobs (
            source,
            mode,
            status,
            message,
            max_pages,
            max_ads,
            pages_discovered,
            ads_discovered,
            ads_processed,
            ads_inserted,
            ads_updated,
            error_count,
            blocked_count,       
            cancel_requested
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
    """, (
        source,
        mode,
        "pending",
        "Job creat",
        max_pages,
        max_ads,
    ))
    job_id = cursor.lastrowid

    conn.commit()
    conn.close()

    crawler = get_crawler(source)

    if not crawler:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE crawl_jobs
            SET status = ?, message = ?, finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, ("failed", f"Sursa necunoscuta: {source}", job_id))
        conn.commit()
        conn.close()

        return {
            "job_id": job_id,
            "status": "failed",
            "message": "Sursa necunoscuta",
        }

    thread = Thread(
        target=run_crawler_with_duplicate_detection,
        args=(crawler, job_id, max_pages, max_ads, mode),
        daemon=True,
    )
    thread.start()


    return {
        "job_id": job_id,
        "status": "started",
        "source": source,
        "mode": mode,
        "max_pages": max_pages,
        "max_ads": max_ads,
    }


@app.post("/crawl/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM crawl_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"error": "Job inexistent"}

    if row["status"] in ("done", "failed", "cancelled"):
        conn.close()
        return {
            "job_id": job_id,
            "status": row["status"],
            "message": "Jobul este deja finalizat"
        }

    cursor.execute("""
        UPDATE crawl_jobs
        SET cancel_requested = 1,
            status = ?,
            message = ?
        WHERE id = ?
    """, ("cancelling", "S-a cerut oprirea jobului", job_id))

    conn.commit()
    conn.close()

    return {
        "job_id": job_id,
        "status": "cancelling",
        "message": "Cererea de oprire a fost trimisa"
    }


@app.get("/crawl/jobs")
def get_jobs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM crawl_jobs
        ORDER BY id DESC
    """)
    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jobs


@app.get("/crawl/jobs/{job_id}")
def get_job(job_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM crawl_jobs
        WHERE id = ?
    """, (job_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"error": "Job inexistent"}

    return dict(row)


@app.get("/statistics")
def get_statistics():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total_ads FROM ads")
    total_ads = cursor.fetchone()["total_ads"]

    cursor.execute("""
        SELECT
            neighborhood,
            COUNT(*) AS count_ads,
            ROUND(AVG(price_eur), 2) AS avg_price,
            ROUND(AVG(surface_mp), 2) AS avg_surface,
            ROUND(AVG(price_eur / surface_mp), 2) AS avg_price_per_mp
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
            AND neighborhood IS NOT NULL
          AND price_eur IS NOT NULL
          AND surface_mp IS NOT NULL
          AND surface_mp > 0
        GROUP BY neighborhood
        ORDER BY count_ads DESC
    """)
    by_neighborhood = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT
            rooms,
            COUNT(*) AS count_ads,
            ROUND(AVG(price_eur), 2) AS avg_price,
            ROUND(AVG(surface_mp), 2) AS avg_surface
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
        AND rooms IS NOT NULL
        GROUP BY rooms
        ORDER BY rooms
    """)
    by_rooms = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT
            source,
            COUNT(*) AS count_ads
        FROM ads
        GROUP BY source
        ORDER BY count_ads DESC
    """)
    by_source = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT
            COUNT(DISTINCT duplicate_group_id) AS duplicate_groups,
            COUNT(*) AS duplicate_ads
        FROM ads
        WHERE duplicate_group_id IS NOT NULL
    """)
    duplicate_summary = dict(cursor.fetchone())

    conn.close()

    return {
        "total_ads": total_ads,
        "by_neighborhood": by_neighborhood,
        "by_rooms": by_rooms,
        "by_source": by_source,
        "duplicates": duplicate_summary,
    }


@app.get("/audit/data-quality")
def read_data_quality_audit():
    return get_data_quality_audit()


@app.get("/favorites")
def get_favorites(current_user=Depends(require_user)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ads.*, favorite_ads.created_at AS favorited_at
        FROM favorite_ads
        JOIN ads ON ads.id = favorite_ads.ad_id
        WHERE favorite_ads.user_id = ?
          AND COALESCE(ads.is_active, 1) = 1
        ORDER BY favorite_ads.created_at DESC
    """, (current_user["id"],))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"items": items, "total": len(items)}


@app.post("/favorites/{ad_id}")
def add_favorite(ad_id: int, current_user=Depends(require_user)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM ads WHERE id = ?", (ad_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Anunt inexistent")

    cursor.execute("""
        INSERT OR IGNORE INTO favorite_ads (user_id, ad_id)
        VALUES (?, ?)
    """, (current_user["id"], ad_id))
    conn.commit()
    conn.close()
    return {"ad_id": ad_id, "is_favorite": True}


@app.delete("/favorites/{ad_id}")
def remove_favorite(ad_id: int, current_user=Depends(require_user)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM favorite_ads WHERE user_id = ? AND ad_id = ?",
        (current_user["id"], ad_id),
    )
    conn.commit()
    conn.close()
    return {"ad_id": ad_id, "is_favorite": False}


@app.get("/admin/statistics")
def get_admin_statistics(current_user=Depends(require_admin)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()["total_users"]

    cursor.execute("SELECT COUNT(*) AS total_favorites FROM favorite_ads")
    total_favorites = cursor.fetchone()["total_favorites"]

    cursor.execute("""
        SELECT
            COUNT(*) AS total_ads,
            SUM(CASE WHEN COALESCE(is_active, 1) = 1 THEN 1 ELSE 0 END) AS active_ads,
            SUM(CASE WHEN COALESCE(is_active, 1) = 0 THEN 1 ELSE 0 END) AS inactive_ads,
            ROUND(AVG(CASE WHEN surface_mp > 0 THEN price_eur * 1.0 / surface_mp ELSE NULL END), 2) AS avg_price_per_mp
        FROM ads
    """)
    summary = dict(cursor.fetchone())

    cursor.execute("""
        SELECT
            neighborhood,
            COUNT(*) AS count_ads,
            ROUND(AVG(price_eur), 2) AS avg_price,
            ROUND(MIN(price_eur), 2) AS min_price,
            ROUND(MAX(price_eur), 2) AS max_price,
            ROUND(AVG(CASE WHEN surface_mp > 0 THEN price_eur * 1.0 / surface_mp ELSE NULL END), 2) AS avg_price_per_mp
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND neighborhood IS NOT NULL
          AND price_eur IS NOT NULL
        GROUP BY neighborhood
        ORDER BY count_ads DESC
        LIMIT 20
    """)
    price_by_neighborhood = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT
            CASE
                WHEN surface_mp < 40 THEN 'sub 40 mp'
                WHEN surface_mp < 55 THEN '40-54 mp'
                WHEN surface_mp < 70 THEN '55-69 mp'
                WHEN surface_mp < 90 THEN '70-89 mp'
                ELSE '90+ mp'
            END AS surface_bucket,
            COUNT(*) AS count_ads,
            ROUND(AVG(price_eur), 2) AS avg_price,
            ROUND(AVG(CASE WHEN surface_mp > 0 THEN price_eur * 1.0 / surface_mp ELSE NULL END), 2) AS avg_price_per_mp
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND surface_mp IS NOT NULL
          AND price_eur IS NOT NULL
        GROUP BY surface_bucket
        ORDER BY MIN(surface_mp)
    """)
    price_by_surface = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT source, COUNT(*) AS count_ads
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
        GROUP BY source
        ORDER BY count_ads DESC
    """)
    by_source = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT status, COUNT(*) AS count_jobs
        FROM crawl_jobs
        GROUP BY status
        ORDER BY count_jobs DESC
    """)
    jobs_by_status = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "users": {
            "total_users": total_users,
            "total_favorites": total_favorites,
        },
        "ads": summary,
        "by_source": by_source,
        "price_by_neighborhood": price_by_neighborhood,
        "price_by_surface": price_by_surface,
        "jobs_by_status": jobs_by_status,
    }


@app.post("/estimate")
def estimate_apartment(payload: EstimateRequest):
    result = estimate_price(payload.dict())
    return result


@app.post("/estimate/ml")
def estimate_apartment_ml(payload: EstimateRequest):
    return predict_ml_price(payload.dict())


@app.post("/ml/train")
def train_price_ml_model(min_samples: int = 80):
    return train_ml_price_model(min_samples=min_samples)


@app.get("/ml/status")
def read_ml_model_status():
    return get_ml_model_status()


@app.post("/duplicates/detect")
def run_duplicate_detection(threshold: int = 92):
    return detect_duplicate_groups(threshold=threshold)


@app.get("/duplicates/groups")
def read_duplicate_groups():
    groups = get_duplicate_groups()
    return {
        "total_groups": len(groups),
        "groups": groups,
    }


@app.get("/duplicates/rejected")
def read_rejected_duplicates(limit: int = 100):
    items = get_rejected_duplicate_ads(limit=limit)
    return {
        "total": len(items),
        "items": items,
    }


@app.get("/map/neighborhoods")
def get_map_neighborhoods(
    neighborhood: Optional[str] = None,
    rooms: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_surface: Optional[float] = None,
    max_surface: Optional[float] = None,
    source: Optional[str] = None,
    city: Optional[str] = None,
    min_confidence: Optional[str] = "low",
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            neighborhood,
            city,
            COUNT(*) AS count_ads,
            ROUND(AVG(price_eur), 2) AS avg_price,
            ROUND(AVG(surface_mp), 2) AS avg_surface,
            ROUND(AVG(
                CASE
                    WHEN surface_mp IS NOT NULL AND surface_mp > 0
                    THEN price_eur * 1.0 / surface_mp
                    ELSE NULL
                END
            ), 2) AS avg_price_per_mp,
            SUM(CASE WHEN location_confidence = 'high' THEN 1 ELSE 0 END) AS high_confidence_count,
            SUM(CASE WHEN location_confidence = 'medium' THEN 1 ELSE 0 END) AS medium_confidence_count,
            SUM(CASE WHEN location_confidence = 'low' THEN 1 ELSE 0 END) AS low_confidence_count
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
            AND neighborhood IS NOT NULL
    """
    params = []

    query, params = apply_ads_filters(
        query,
        params,
        neighborhood=neighborhood,
        rooms=rooms,
        min_price=min_price,
        max_price=max_price,
        min_surface=min_surface,
        max_surface=max_surface,
        source=source,
        city=city,
        min_confidence=min_confidence,
    )

    query += """
        GROUP BY neighborhood, city
        ORDER BY count_ads DESC, neighborhood ASC
    """

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {
        "filters": {
            "neighborhood": neighborhood,
            "rooms": rooms,
            "min_price": min_price,
            "max_price": max_price,
            "min_surface": min_surface,
            "max_surface": max_surface,
            "source": source,
            "city": city,
            "min_confidence": min_confidence,
        },
        "total_neighborhoods": len(rows),
        "items": rows,
    }


@app.get("/map/neighborhoods/points")
def get_map_neighborhood_points(
    neighborhood: Optional[str] = None,
    rooms: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_surface: Optional[float] = None,
    max_surface: Optional[float] = None,
    source: Optional[str] = None,
    city: Optional[str] = None,
    min_confidence: Optional[str] = "low",
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            neighborhood,
            city,
            COUNT(*) AS count_ads,
            ROUND(AVG(price_eur), 2) AS avg_price,
            ROUND(AVG(surface_mp), 2) AS avg_surface,
            ROUND(AVG(
                CASE
                    WHEN surface_mp IS NOT NULL AND surface_mp > 0
                    THEN price_eur * 1.0 / surface_mp
                    ELSE NULL
                END
            ), 2) AS avg_price_per_mp,
            SUM(CASE WHEN location_confidence = 'high' THEN 1 ELSE 0 END) AS high_confidence_count,
            SUM(CASE WHEN location_confidence = 'medium' THEN 1 ELSE 0 END) AS medium_confidence_count,
            SUM(CASE WHEN location_confidence = 'low' THEN 1 ELSE 0 END) AS low_confidence_count
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
            AND neighborhood IS NOT NULL
    """
    params = []

    query, params = apply_ads_filters(
        query,
        params,
        neighborhood=neighborhood,
        rooms=rooms,
        min_price=min_price,
        max_price=max_price,
        min_surface=min_surface,
        max_surface=max_surface,
        source=source,
        city=city,
        min_confidence=min_confidence,
    )

    query += """
        GROUP BY neighborhood, city
        ORDER BY count_ads DESC, neighborhood ASC
    """

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    items = []

    for row in rows:
        config = NEIGHBORHOODS.get(row["neighborhood"])
        if not config:
            continue

        centroid = config.get("centroid")
        if not centroid:
            continue

        latitude, longitude = centroid

        items.append({
            "neighborhood": row["neighborhood"],
            "city": row["city"],
            "centroid": centroid,
            "latitude": latitude,
            "longitude": longitude,
            "count_ads": row["count_ads"],
            "avg_price": row["avg_price"],
            "avg_surface": row["avg_surface"],
            "avg_price_per_mp": row["avg_price_per_mp"],
            "high_confidence_count": row["high_confidence_count"],
            "medium_confidence_count": row["medium_confidence_count"],
            "low_confidence_count": row["low_confidence_count"],
            "radius": build_point_radius(row["count_ads"]),
        })

    map_view = get_map_view_for_city(city)

    return {
        "filters": {
            "neighborhood": neighborhood,
            "rooms": rooms,
            "min_price": min_price,
            "max_price": max_price,
            "min_surface": min_surface,
            "max_surface": max_surface,
            "source": source,
            "city": city,
            "min_confidence": min_confidence,
        },
        "map_view": map_view,
        "total_points": len(items),
        "items": items,
    }
