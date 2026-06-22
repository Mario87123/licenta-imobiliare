import json
import random
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from playwright.sync_api import sync_playwright

from .database import get_connection
from .crawler_job_utils import (
    update_job,
    increment_job_field,
    is_cancel_requested,
    resolve_crawl_limits,
    should_stop_early,
)
from .location_resolver import resolve_location, normalize_text
from .duplicate_detector import (
    find_existing_duplicate_for_ad,
    save_rejected_duplicate_ad,
)


BASE_URL = "https://www.storia.ro"
START_URL = "https://www.storia.ro/ro/rezultate/vanzare/apartament/timis/timisoara?distanceRadius=15"


def build_listing_url(page_no: int):
    if page_no <= 1:
        return START_URL

    parsed = urlparse(START_URL)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page_no)

    return urlunparse(parsed._replace(query=urlencode(query)))


def parse_price(text: str):
    if not text:
        return None

    normalized_text = (
        text.replace("\xa0", " ")
        .replace("â‚¬", " eur ")
        .replace("EUR", " eur ")
        .replace("Euro", " eur ")
        .replace("EURO", " eur ")
    )

    patterns = [
        r"(\d[\d\s\.,]*)\s*(?:eur|euro)",
        r"(?:eur|euro)\s*(\d[\d\s\.,]*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if not match:
            continue

        raw_value = match.group(1)
        digits_only = re.sub(r"[^\d]", "", raw_value)

        if not digits_only:
            continue

        try:
            price = int(digits_only)
        except ValueError:
            continue

        if 10000 <= price <= 2000000:
            return price

    return None


def parse_surface(text: str, title: str = ""):
    if not text:
        return None

    search_text = normalize_text(text)

    patterns = [
        r"\bsuprafata\s+utila\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*(?:mp|m2|m\^2)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, search_text, re.IGNORECASE)
        if not match:
            continue

        try:
            value = float(match.group(1).replace(",", "."))
        except ValueError:
            continue

        if 10 <= value <= 500:
            return value

    return None

def parse_rooms(text: str):
    if not text:
        return None

    patterns = [
        r"(\d+)\s*cam(?:era|ere)?",
        r"num[aÄƒ]rul de camere\s*(\d+)",
    ]

    lowered = text.lower()

    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            try:
                rooms = int(match.group(1))
            except ValueError:
                continue

            if 1 <= rooms <= 10:
                return rooms

    return None


def parse_floor(text: str):
    if not text:
        return None

    patterns = [
        r"etaj\s*[:\-]?\s*parter",
        r"parter\s*/\s*\d+",
        r"(\d+)\s*etajul",
        r"etaj\s*[:\-]?\s*(\d+)",
    ]

    lowered = text.lower()

    if re.search(patterns[0], lowered) or re.search(patterns[1], lowered):
        return 0

    for pattern in patterns[2:]:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            try:
                floor = int(match.group(1))
            except ValueError:
                continue

            if 0 <= floor <= 60:
                return floor

    return None


def parse_total_floors(text: str):
    if not text:
        return None

    patterns = [
        r"etaj\s+\d+\s*/\s*(\d+)",
        r"(\d+)\s*din\s*(\d+)",
    ]

    lowered = text.lower()

    match = re.search(patterns[0], lowered, re.IGNORECASE)
    if match:
        try:
            total = int(match.group(1))
        except ValueError:
            return None
        return total if 1 <= total <= 60 else None

    match = re.search(patterns[1], lowered, re.IGNORECASE)
    if match:
        try:
            total = int(match.group(2))
        except ValueError:
            return None
        return total if 1 <= total <= 60 else None

    return None


def safe_locator_text(page, selector: str):
    try:
        locator = page.locator(selector)
        if locator.count() > 0:
            text = locator.first.inner_text().strip()
            return text or None
    except Exception:
        return None
    return None


def safe_locator_attr(page, selector: str, attr: str):
    try:
        locator = page.locator(selector)
        if locator.count() > 0:
            value = locator.first.get_attribute(attr)
            if value:
                value = value.strip()
                return value or None
    except Exception:
        return None
    return None


def clean_header_location_candidate(value: str):
    if not value:
        return None

    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None

    normalized = normalize_text(value)

    blocked_markers = [
        "calculeaza rata",
        "publicitate",
        "relevee",
        "salveaza",
        "distribuie",
        "raporteaza",
        "contacteaza",
        "anunturi similare",
        "mai multe anunturi",
        "eur",
        "euro",
        "€/m",
    ]

    if any(marker in normalized for marker in blocked_markers):
        return None

    value = re.sub(r"\bVezi\s+Hart[a\u0103]\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" -,\n\t")

    if not value or len(value) > 180:
        return None

    normalized = normalize_text(value)

    if not (
        "timisoara" in normalized
        or "timis" in normalized
        or "," in value
    ):
        return None

    return value


def extract_header_location_text(page):
    selector_candidates = [
        "[data-testid*='location' i]",
        "[class*='location' i]",
        "[class*='address' i]",
        "a[href*='harta']",
        "a[href*='map']",
    ]

    for selector in selector_candidates:
        try:
            locator = page.locator(selector)
            count = min(locator.count(), 10)

            for i in range(count):
                candidate = clean_header_location_candidate(locator.nth(i).inner_text())
                if candidate:
                    return candidate
        except Exception:
            continue

    try:
        candidates = page.evaluate("""
            () => {
                const h1 = document.querySelector("h1");
                if (!h1) return [];

                const titleText = (h1.innerText || "").replace(/\\s+/g, " ").trim();
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0;
                };

                const clean = (text) => (text || "").replace(/\\s+/g, " ").trim();
                const looksLikeLocation = (value) => {
                    if (!value || value === titleText || value.length > 180) return false;
                    if (!/timisoara|timis|,/i.test(value)) return false;
                    if (/eur|euro|€|\\bmp\\b|m²|m2|publicitate|calculeaza rata|salveaza|distribuie/i.test(value)) return false;
                    return true;
                };

                const results = [];
                const pushText = (text) => {
                    const value = clean(text);
                    if (looksLikeLocation(value)) results.push(value);
                };

                let sibling = h1.nextElementSibling;
                for (let i = 0; sibling && i < 12; i += 1) {
                    if (isVisible(sibling)) {
                        pushText(sibling.innerText);

                        for (const node of Array.from(sibling.querySelectorAll("a, span, p, div")).slice(0, 60)) {
                            if (isVisible(node)) pushText(node.innerText);
                        }
                    }
                    sibling = sibling.nextElementSibling;
                }

                let container = h1.parentElement;
                for (let depth = 0; container && depth < 5; depth += 1) {
                    const nodes = Array.from(container.querySelectorAll("a, span, p, div"));

                    for (const node of nodes.slice(0, 120)) {
                        if (node === h1 || node.contains(h1) || !isVisible(node)) continue;
                        pushText(node.innerText);
                    }

                    container = container.parentElement;
                }

                return [...new Set(results)];
            }
        """)

        for value in candidates:
            candidate = clean_header_location_candidate(value)
            if candidate:
                return candidate
    except Exception:
        return None

    return None


def resolve_storia_location(title: str, text: str, header_location: str | None):
    if header_location:
        location_info = resolve_location(f"zona {header_location}", "")
        if location_info["neighborhood"] is not None:
            location_info["location_confidence"] = "high"
            return location_info, "header"

    location_info = resolve_location(title or "", "")
    if location_info["neighborhood"] is not None:
        return location_info, "title"

    return resolve_location("", text or ""), "description"


def clean_title_candidate(value: str):
    if not value:
        return None

    value = value.strip()
    value = re.sub(r"\s*\|\s*Storia(?:\.ro)?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*-\s*Storia(?:\.ro)?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s{2,}", " ", value).strip()

    if not value:
        return None

    bad_values = {
        "storia",
        "storia.ro",
        "anunt",
        "anunÈ›",
    }

    if value.lower() in bad_values:
        return None

    return value

def is_generic_storia_title(title: str) -> bool:
    if not title:
        return False

    normalized = normalize_text(title)

    generic_titles = [
        "storia.ro - anunturi imobiliare pentru apartamente, case, terenuri",
        "storia.ro - anunturi imobiliare",
        "anunturi imobiliare pentru apartamente, case, terenuri",
    ]

    return any(generic in normalized for generic in generic_titles)


def extract_json_ld_objects(page):
    objects = []

    try:
        scripts = page.locator("script[type='application/ld+json']")
        count = scripts.count()

        for i in range(count):
            raw = scripts.nth(i).inner_text().strip()
            if not raw:
                continue

            try:
                parsed = json.loads(raw)
            except Exception:
                continue

            candidates = []

            if isinstance(parsed, dict):
                candidates.append(parsed)

                graph = parsed.get("@graph")
                if isinstance(graph, list):
                    candidates.extend(item for item in graph if isinstance(item, dict))

            elif isinstance(parsed, list):
                candidates.extend(item for item in parsed if isinstance(item, dict))

            for item in candidates:
                objects.append(item)

    except Exception:
        return []

    return objects


def extract_title_from_json_ld(objects):
    for obj in objects:
        for key in ("name", "headline"):
            value = obj.get(key)
            if isinstance(value, str):
                cleaned = clean_title_candidate(value)
                if cleaned and len(cleaned) >= 8:
                    return cleaned
    return None


def parse_price_value(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        value = int(value)
        if 10000 <= value <= 2000000:
            return value
        return None

    if isinstance(value, str):
        return parse_price(value)

    return None


def extract_price_from_json_ld(objects):
    for obj in objects:
        direct_price = parse_price_value(obj.get("price"))
        if direct_price:
            return direct_price

        offers = obj.get("offers")
        if isinstance(offers, dict):
            for key in ("price", "lowPrice", "highPrice"):
                candidate = parse_price_value(offers.get(key))
                if candidate:
                    return candidate

        if isinstance(offers, list):
            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                for key in ("price", "lowPrice", "highPrice"):
                    candidate = parse_price_value(offer.get(key))
                    if candidate:
                        return candidate

    return None


def extract_listing_links_from_json_ld(objects):
    links = []

    for obj in objects:
        if obj.get("@type") != "ItemList":
            continue

        elements = obj.get("itemListElement", [])
        if not isinstance(elements, list):
            continue

        for item in elements:
            if not isinstance(item, dict):
                continue

            url = item.get("url")

            if not url and isinstance(item.get("item"), dict):
                url = item["item"].get("@id") or item["item"].get("url")

            if isinstance(url, str) and url.startswith(BASE_URL):
                links.append(url.split("?")[0])

    return links


def extract_listing_links(page):
    json_ld_objects = extract_json_ld_objects(page)
    json_ld_links = extract_listing_links_from_json_ld(json_ld_objects)

    def is_valid_storia_ad_url(url: str) -> bool:
        if not url:
            return False

        normalized = url.split("?")[0].strip()

        if not normalized.startswith(BASE_URL):
            return False

        if "/ro/oferta/" not in normalized:
            return False

        if "-ID" not in normalized:
            return False

        blocked_fragments = [
            "/ro/rezultate/",
            "/ro/agentii/",
            "/ro/dezvoltator/",
            "/ro/firmy/",
            "/ro/blog/",
            "/contact",
            "/mapa",
            "/harta",
        ]

        if any(fragment in normalized for fragment in blocked_fragments):
            return False

        return True

    if json_ld_links:
        unique = []
        seen = set()

        for link in json_ld_links:
            if not is_valid_storia_ad_url(link):
                continue

            if link not in seen:
                seen.add(link)
                unique.append(link)

        return unique

    href_items = page.locator("a[href]").evaluate_all("""
        els => els.map(a => ({
            href: a.href,
            text: (a.innerText || "").trim()
        }))
    """)

    links = []

    for item in href_items:
        href = item.get("href")
        if not href:
            continue

        href = urljoin(BASE_URL, href).split("?")[0].strip()

        if not is_valid_storia_ad_url(href):
            continue

        links.append(href)

    unique = []
    seen = set()

    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    return unique


def is_blocked_page(text: str):
    if not text:
        return False

    preview = normalize_text(text[:1500])

    blocked_markers = [
        "403",
        "access denied",
        "forbidden",
        "too many requests",
        "temporarily unavailable",
        "verification",
        "captcha",
        "blocked",
    ]

    return any(marker in preview for marker in blocked_markers)


def load_detail_page_with_retry(detail_page, ad_url, retries: int = 2):
    for attempt in range(retries + 1):
        try:
            detail_page.goto(ad_url, timeout=18000, wait_until="domcontentloaded")
            detail_page.wait_for_timeout(random.randint(900, 1400))

            text = detail_page.locator("body").inner_text()

            if is_blocked_page(text):
                raise RuntimeError("blocked_page")

            return text, False

        except Exception as exc:
            was_blocked = "blocked_page" in str(exc).lower() or "403" in str(exc)

            if attempt == retries:
                return None, was_blocked

            backoff_ms = random.randint(1800, 3200) * (attempt + 1)
            print(f"[STORIA] Retry {attempt + 1}/{retries} pentru {ad_url} dupa {backoff_ms}ms")
            detail_page.wait_for_timeout(backoff_ms)

    return None, False

def extract_primary_listing_text(text: str):
    if not text:
        return ""

    cut_markers = [
        "AnunÈ›uri similare",
        "Anunturi similare",
        "Mai multe anunÈ›uri de la",
        "Mai multe anunturi de la",
        "Alte anunÈ›uri",
        "Alte anunturi",
        "Vezi toate anunÈ›urile",
        "Vezi toate anunturile",
    ]

    cut_index = len(text)

    for marker in cut_markers:
        idx = text.find(marker)
        if idx != -1 and idx < cut_index:
            cut_index = idx

    return text[:cut_index].strip()


def extract_ad_details(detail_page, ad_url):
    raw_text = detail_page.locator("body").inner_text()
    text = extract_primary_listing_text(raw_text)
    json_ld_objects = extract_json_ld_objects(detail_page)

    title_candidates = [
        safe_locator_text(detail_page, "h1"),
        safe_locator_attr(detail_page, "meta[property='og:title']", "content"),
        safe_locator_attr(detail_page, "meta[name='twitter:title']", "content"),
        safe_locator_attr(detail_page, "meta[name='title']", "content"),
        extract_title_from_json_ld(json_ld_objects),
    ]

    try:
        title_candidates.append(detail_page.title())
    except Exception:
        pass

    title = None
    for candidate in title_candidates:
        cleaned = clean_title_candidate(candidate)
        if cleaned and len(cleaned) >= 8:
            title = cleaned
            break

    if is_generic_storia_title(title or ""):
        save_ignored_url(
            ad_url,
            "generic_storia_page",
            source="storia",
        )
        print(f"[STORIA] Pagina generica ignorata: {ad_url}")
        return None


    price = (
        extract_price_from_json_ld(json_ld_objects)
        or parse_price(text)
        or parse_price(title or "")
    )

    surface = parse_surface(text)
    rooms = parse_rooms(f"{title or ''}\n{text or ''}")
    floor = parse_floor(text)
    total_floors = parse_total_floors(text)

    header_location = extract_header_location_text(detail_page)
    location_info, location_source = resolve_storia_location(title or "", text or "", header_location)
    neighborhood = location_info["neighborhood"]
    city = location_info["city"]
    nearby_neighborhood = location_info["nearby_neighborhood"]
    location_confidence = location_info["location_confidence"]

    if price is not None and (price < 10000 or price > 2000000):
        price = None

    if surface is not None and (surface < 10 or surface > 500):
        surface = None

    if rooms is not None and (rooms < 1 or rooms > 10):
        rooms = None

    if floor is not None and (floor < -2 or floor > 60):
        floor = None

    if total_floors is not None and (total_floors < 1 or total_floors > 60):
        total_floors = None

    if not title:
        print("[STORIA] Lipseste title")
    if not price:
        print("[STORIA] Lipseste price")
    if neighborhood is None:
        print("[STORIA] Neighborhood negasit")
        print(f"TITLE: {title}")
        if header_location:
            print(f"HEADER LOCATION: {header_location}")
    else:
        print(
            f"[STORIA] Cartier detectat din {location_source}: "
            f"{neighborhood} ({header_location or title or 'descriere'})"
        )

    if not title or not price or neighborhood is None:
        reason_parts = []

        if not title:
            reason_parts.append("missing_title")
        if not price:
            reason_parts.append("missing_price")
        if neighborhood is None:
            reason_parts.append("missing_neighborhood")

        save_ignored_url(
            ad_url,
            ",".join(reason_parts) or "invalid_listing",
            source="storia",
        )
        return None


    return {
        "title": title,
        "price_eur": price,
        "surface_mp": surface,
        "rooms": rooms,
        "neighborhood": neighborhood,
        "city": city,
        "nearby_neighborhood": nearby_neighborhood,
        "location_confidence": location_confidence,
        "floor": floor,
        "total_floors": total_floors,
        "year_built": None,
        "partitioning": None,
        "url": ad_url,
        "source": "storia",
    }


def get_existing_urls(urls):
    if not urls:
        return set()

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" for _ in urls)
    cursor.execute(
        f"SELECT url FROM ads WHERE url IN ({placeholders})",
        urls,
    )

    existing = {row["url"] for row in cursor.fetchall()}
    conn.close()
    return existing

def get_ignored_urls(urls, source: str = "storia"):
    if not urls:
        return set()

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" for _ in urls)
    cursor.execute(
        f"""
        SELECT url
        FROM ignored_listing_urls
        WHERE source = ?
          AND url IN ({placeholders})
        """,
        [source, *urls],
    )

    ignored = {row["url"] for row in cursor.fetchall()}
    conn.close()
    return ignored


def save_ignored_url(url: str, reason: str, source: str = "storia"):
    if not url:
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ignored_listing_urls (url, source, reason)
        VALUES (?, ?, ?)
        ON CONFLICT(url, source) DO UPDATE SET
            reason = excluded.reason
    """, (url, source, reason))

    conn.commit()
    conn.close()


def mark_existing_urls_seen(urls):
    if not urls:
        return 0

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" for _ in urls)
    cursor.execute(
        f"""
        UPDATE ads
        SET
            last_seen_at = CURRENT_TIMESTAMP,
            last_crawled_at = CURRENT_TIMESTAMP,
            is_active = 1
        WHERE url IN ({placeholders})
        """,
        urls,
    )

    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected


def save_ads(ads):
    if not ads:
        return 0, 0

    urls = [ad["url"] for ad in ads]
    existing_urls = get_existing_urls(urls)
    ads_to_save = []

    for ad in ads:
        was_existing = ad["url"] in existing_urls

        if not was_existing:
            duplicate_match = find_existing_duplicate_for_ad(ad)
            if duplicate_match:
                save_rejected_duplicate_ad(ad, duplicate_match, source_label=ad.get("source"))
                matched_ad = duplicate_match["matched_ad"]
                print(
                    f"[{ad.get('source', 'CRAWLER').upper()}] Duplicat cross-source blocat: "
                    f"matched_ad_id={matched_ad['id']} score={duplicate_match['score']} url={ad.get('url')}"
                )
                continue

        ads_to_save.append((ad, was_existing))

    if not ads_to_save:
        return 0, 0

    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    updated = 0

    for ad, was_existing in ads_to_save:
        cursor.execute("""
            INSERT INTO ads (
                title, price_eur, surface_mp, rooms, neighborhood,
                city, nearby_neighborhood, location_confidence,
                floor, total_floors, year_built, partitioning, url, source,
                first_seen_at, last_seen_at, last_crawled_at, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                price_eur = excluded.price_eur,
                surface_mp = excluded.surface_mp,
                rooms = excluded.rooms,
                neighborhood = excluded.neighborhood,
                city = excluded.city,
                nearby_neighborhood = excluded.nearby_neighborhood,
                location_confidence = excluded.location_confidence,
                floor = excluded.floor,
                total_floors = excluded.total_floors,
                year_built = excluded.year_built,
                partitioning = excluded.partitioning,
                source = excluded.source,
                last_seen_at = CURRENT_TIMESTAMP,
                last_crawled_at = CURRENT_TIMESTAMP,
                is_active = 1
        """, (
            ad["title"],
            ad["price_eur"],
            ad["surface_mp"],
            ad["rooms"],
            ad["neighborhood"],
            ad["city"],
            ad["nearby_neighborhood"],
            ad["location_confidence"],
            ad["floor"],
            ad["total_floors"],
            ad["year_built"],
            ad["partitioning"],
            ad["url"],
            ad["source"],
        ))

        if was_existing:
            updated += 1
        else:
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, updated


def run_storia_crawler(
    job_id: int,
    max_pages: int | None = None,
    max_ads: int | None = None,
    mode: str = "quick_refresh",
):
    try:
        resolved_max_pages, resolved_max_ads = resolve_crawl_limits(
            mode, max_pages, max_ads
        )

        update_job(
            job_id,
            status="running",
            message="Crawler Storia ruleaza",
            source="storia",
            mode=mode,
            max_pages=resolved_max_pages,
            max_ads=resolved_max_ads,
            pages_discovered=0,
            ads_discovered=0,
            ads_processed=0,
            ads_inserted=0,
            ads_updated=0,
            error_count=0,
            blocked_count=0,
        )

        all_ads = []
        new_links_to_process = []
        cancelled = False
        consecutive_duplicate_pages = 0
        consecutive_blocked_details = 0
        max_consecutive_blocked_details = 5
        stop_reason = None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="ro-RO",
                timezone_id="Europe/Bucharest",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={
                    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7"
                }
            )

            def handle_route(route):
                request = route.request
                resource_type = request.resource_type
                url = request.url.lower()

                blocked_resource_type = {"image", "media", "font"}
                blocked_domains = [
                    "googletagmanager.com",
                    "google-analytics.com",
                    "doubleclick.net",
                    "facebook.net",
                    "facebook.com/tr",
                ]

                if resource_type in blocked_resource_type:
                    route.abort()
                    return

                if any(domain in url for domain in blocked_domains):
                    route.abort()
                    return

                route.continue_()

            context.route("**/*", handle_route)

            page = context.new_page()

            for page_no in range(1, resolved_max_pages + 1):
                if is_cancel_requested(job_id):
                    cancelled = True
                    break

                if resolved_max_ads is not None and len(new_links_to_process) >= resolved_max_ads:
                    stop_reason = "A fost atinsa limita maxima de anunturi noi pentru acest job"
                    break

                url = build_listing_url(page_no)

                print(f"[STORIA] Deschid pagina de listare: {url}")

                page.goto(url, timeout=22000, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)

                links = extract_listing_links(page)

                page_unique_links = []
                seen_page = set()
                for link in links:
                    if link not in seen_page:
                        seen_page.add(link)
                        page_unique_links.append(link)

                existing_urls = get_existing_urls(page_unique_links)
                ignored_urls = get_ignored_urls(page_unique_links, source="storia")

                mark_existing_urls_seen(list(existing_urls))

                page_new_links = [
                    link
                    for link in page_unique_links
                    if link not in existing_urls and link not in ignored_urls
                ]


                for link in page_new_links:
                    if link not in new_links_to_process:
                        new_links_to_process.append(link)

                if resolved_max_ads is not None:
                    new_links_to_process = new_links_to_process[:resolved_max_ads]

                if len(page_new_links) == 0:
                    consecutive_duplicate_pages += 1
                else:
                    consecutive_duplicate_pages = 0

                update_job(
                    job_id,
                    pages_discovered=page_no,
                    ads_discovered=len(new_links_to_process),
                    message=(
                        f"STORIA [{mode}]: pagina {page_no}/{resolved_max_pages}, "
                        f"linkuri pe pagina: {len(page_unique_links)}, "
                        f"noi: {len(page_new_links)}, "
                        f"existente: {len(existing_urls)}, "
                        f"ignorate: {len(ignored_urls)}, "
                        f"duplicate consecutive: {consecutive_duplicate_pages}"
                    ),
                )

                print(
                    f"[STORIA] Pagina {page_no}: total={len(page_unique_links)}, "
                    f"noi={len(page_new_links)}, duplicate consecutive={consecutive_duplicate_pages}"
                )

                if should_stop_early(mode, consecutive_duplicate_pages):
                    stop_reason = (
                        f"Oprire automata: {consecutive_duplicate_pages} pagini consecutive fara anunturi noi"
                    )
                    break

                page.wait_for_timeout(random.randint(700, 1300))

            if resolved_max_ads is not None:
                new_links_to_process = new_links_to_process[:resolved_max_ads]

            update_job(
                job_id,
                ads_discovered=len(new_links_to_process),
                message=(
                    f"STORIA [{mode}]: urmeaza procesarea a {len(new_links_to_process)} anunturi noi"
                ),
            )

            print(f"[STORIA] Total linkuri noi pentru procesare: {len(new_links_to_process)}")
            print(f"[STORIA] Primele linkuri noi: {new_links_to_process[:5]}")

            detail = context.new_page()

            for idx, link in enumerate(new_links_to_process, start=1):
                if is_cancel_requested(job_id):
                    cancelled = True
                    break

                text, was_blocked = load_detail_page_with_retry(detail, link, retries=2)

                if text is None:
                    if was_blocked:
                        increment_job_field(job_id, "blocked_count", 1)
                        consecutive_blocked_details += 1
                        update_job(
                            job_id,
                            ads_processed=idx,
                            message=(
                                f"STORIA [{mode}]: pagina blocata pentru anuntul {idx}/{len(new_links_to_process)}"
                            ),
                        )
                        print(f"[STORIA] Pagina blocata pentru: {link}")

                        if consecutive_blocked_details >= max_consecutive_blocked_details:
                            stop_reason = (
                                f"Oprire automata: {consecutive_blocked_details} pagini de detaliu blocate consecutiv"
                            )
                            break
                    else:
                        increment_job_field(job_id, "error_count", 1)
                        update_job(
                            job_id,
                            ads_processed=idx,
                            message=(
                                f"STORIA [{mode}]: eroare la anuntul {idx}/{len(new_links_to_process)}"
                            ),
                        )
                        print(f"[STORIA] ({idx}) Eroare la {link}: pagina nu a putut fi incarcata")

                    detail.wait_for_timeout(random.randint(1200, 2200))
                    continue

                consecutive_blocked_details = 0

                try:
                    ad = extract_ad_details(detail, link)

                    if ad:
                        all_ads.append(ad)

                    update_job(
                        job_id,
                        ads_processed=idx,
                        message=(
                            f"STORIA [{mode}]: procesat {idx}/{len(new_links_to_process)} anunturi noi"
                        ),
                    )

                    detail.wait_for_timeout(random.randint(900, 1600))

                except Exception as e:
                    increment_job_field(job_id, "error_count", 1)
                    update_job(
                        job_id,
                        ads_processed=idx,
                        message=(
                            f"STORIA [{mode}]: eroare la parsarea anuntului {idx}/{len(new_links_to_process)}"
                        ),
                    )
                    print(f"[STORIA] ({idx}) Eroare la parsare pentru {link}: {e}")
                    detail.wait_for_timeout(random.randint(1200, 2200))

            detail.close()
            page.close()
            context.close()
            browser.close()

        inserted, updated = save_ads(all_ads)

        update_job(
            job_id,
            ads_inserted=inserted,
            ads_updated=updated,
        )

        if cancelled:
            update_job(
                job_id,
                status="cancelled",
                message=(
                    f"Crawler Storia oprit manual. "
                    f"Anunturi noi descoperite: {len(new_links_to_process)}, "
                    f"procesate: {len(all_ads)}, inserate: {inserted}, actualizate: {updated}"
                ),
                finished=True,
            )
            return

        final_message = (
            f"Crawler Storia terminat [{mode}]. "
            f"Pagini parcurse: {min(resolved_max_pages, page_no if 'page_no' in locals() else 0)}, "
            f"anunturi noi descoperite: {len(new_links_to_process)}, "
            f"procesate: {len(all_ads)}, inserate noi: {inserted}, actualizate: {updated}"
        )

        if stop_reason:
            final_message += f". {stop_reason}"

        update_job(
            job_id,
            status="done",
            message=final_message,
            finished=True,
        )

    except Exception as e:
        update_job(
            job_id,
            status="failed",
            message=f"Eroare STORIA: {str(e)}",
            finished=True,
        )

