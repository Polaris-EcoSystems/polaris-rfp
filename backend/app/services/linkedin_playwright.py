from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any

from playwright.sync_api import sync_playwright


class LinkedInSessionError(RuntimeError):
    pass


def _sleep_jitter(base: float = 0.6, max_jitter: float = 0.6) -> None:
    t = base + (time.time() % max_jitter)
    time.sleep(max(0.1, min(2.0, t)))


def _is_login_url(url: str) -> bool:
    u = (url or "").lower()
    return "/login" in u or "checkpoint" in u


def _ensure_logged_in(page) -> None:
    if _is_login_url(page.url):
        raise LinkedInSessionError("LinkedIn session expired or requires login/checkpoint")


def validate_linkedin_session(
    *,
    storage_state: dict[str, Any],
    headless: bool = True,
    timeout_ms: int = 30_000,
) -> None:
    """
    Validates that the provided storageState can access LinkedIn without redirecting
    to login/checkpoint.

    Raises LinkedInSessionError on invalid/expired session.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=bool(headless))
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        page.goto(
            "https://www.linkedin.com/feed/",
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        _sleep_jitter(0.3, 0.4)
        _ensure_logged_in(page)
        context.close()
        browser.close()


def _first_company_result_url(page) -> str | None:
    links = page.locator('a[href*="/company/"]')
    cnt = links.count()
    for i in range(min(cnt, 10)):
        href = links.nth(i).get_attribute("href") or ""
        if "/company/" in href:
            if href.startswith("/"):
                return f"https://www.linkedin.com{href}"
            if href.startswith("http"):
                return href
    return None


def _company_people_url(company_url: str) -> str:
    u = (company_url or "").strip()
    if not u:
        return ""
    if u.startswith("/"):
        u = f"https://www.linkedin.com{u}"
    if not u.startswith("http"):
        u = f"https://{u}"
    u = u.split("?")[0].rstrip("/")
    if "/company/" not in u:
        return ""
    return f"{u}/people/"


def _extract_people_cards(page, max_people: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    anchors = page.locator('a[href*="/in/"]')
    cnt = anchors.count()
    for i in range(min(cnt, max_people * 3)):
        a = anchors.nth(i)
        href = (a.get_attribute("href") or "").split("?")[0]
        if not href or "/in/" not in href:
            continue
        if href.startswith("/"):
            href = f"https://www.linkedin.com{href}"
        if href in seen_urls:
            continue
        seen_urls.add(href)

        card = a.locator("xpath=ancestor::li[1]")
        if card.count() == 0:
            card = a.locator("xpath=ancestor::div[1]")
        text = ""
        try:
            text = (card.inner_text(timeout=500) or "").strip()
        except Exception:
            try:
                text = (a.inner_text(timeout=500) or "").strip()
            except Exception:
                text = ""

        lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
        name = lines[0] if len(lines) >= 1 else ""
        title = lines[1] if len(lines) >= 2 else ""
        location = lines[2] if len(lines) >= 3 else ""

        name = re.sub(r"\s+", " ", name).strip()
        title = re.sub(r"\s+", " ", title).strip()
        location = re.sub(r"\s+", " ", location).strip()

        profile_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", href).strip("_")[-64:] or None
        out.append(
            {
                "profileUrl": href,
                "profileId": profile_id,
                "name": name,
                "title": title,
                "location": location,
                "source": "linkedin",
            }
        )
        if len(out) >= max_people:
            break

    return out


def discover_people_for_company(
    *,
    storage_state: dict[str, Any],
    company_name: str | None,
    company_linkedin_url: str | None,
    max_people: int = 50,
    headless: bool = True,
    timeout_ms: int = 45_000,
) -> list[dict[str, Any]]:
    max_people = max(1, min(200, int(max_people or 50)))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=bool(headless))
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()

        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=timeout_ms)
        _sleep_jitter()
        _ensure_logged_in(page)

        target_company_url = (company_linkedin_url or "").strip()
        if not target_company_url:
            q = urllib.parse.quote_plus((company_name or "").strip())
            if not q:
                raise ValueError("companyLinkedInUrl or companyName is required")
            search_url = f"https://www.linkedin.com/search/results/companies/?keywords={q}"
            page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
            _sleep_jitter()
            _ensure_logged_in(page)
            try:
                page.wait_for_timeout(800)
            except Exception:
                pass
            found = _first_company_result_url(page)
            if not found:
                raise RuntimeError("Could not find a LinkedIn company result for the provided companyName")
            target_company_url = found

        people_url = _company_people_url(target_company_url)
        if not people_url:
            raise ValueError("companyLinkedInUrl must be a LinkedIn /company/ URL")

        page.goto(people_url, wait_until="domcontentloaded", timeout=timeout_ms)
        _sleep_jitter()
        _ensure_logged_in(page)

        people: list[dict[str, Any]] = []
        last_count = 0
        for _ in range(25):
            batch = _extract_people_cards(page, max_people=max_people)
            by_url = {p["profileUrl"]: p for p in people}
            for b in batch:
                by_url[b["profileUrl"]] = b
            people = list(by_url.values())
            if len(people) >= max_people:
                break

            if len(people) == last_count:
                page.mouse.wheel(0, 2200)
                _sleep_jitter(0.8, 0.8)
                batch2 = _extract_people_cards(page, max_people=max_people)
                if len(batch2) <= len(batch):
                    break
            else:
                last_count = len(people)

            try:
                page.mouse.wheel(0, 2600)
            except Exception:
                pass
            _sleep_jitter(0.7, 0.7)

        context.close()
        browser.close()

    return people[:max_people]

