"""Open the Streamlit demo in a real browser so it wakes up. Never clicks Run."""
import re
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://blastguard-ai.streamlit.app/"
WAKE = re.compile(r"get this app back up", re.I)


def frames(page):
    return [page.main_frame, *page.frames]


def find_wake(page):
    for f in frames(page):
        try:
            b = f.get_by_role("button", name=WAKE)
            if b.count():
                return b.first
        except Exception:
            pass
    return None


def loaded(page):
    for f in frames(page):
        try:
            if "BlastGuard" in (f.inner_text("body", timeout=2000) or ""):
                return True
        except Exception:
            pass
    return False


def dump_debug(page):
    """Leave a screenshot, frame list and visible text so a failure can be diagnosed."""
    try:
        page.screenshot(path="wake-debug.png", full_page=True)
    except Exception as exc:
        print(f"screenshot failed: {exc}")
    for f in frames(page):
        try:
            text = (f.inner_text("body", timeout=3000) or "")[:400].replace("\n", " | ")
        except Exception as exc:
            text = f"<unreadable: {exc}>"
        print(f"frame {f.url}: {text}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        print(f"opened {page.url}")
        clicked = False
        deadline = time.time() + 90
        while time.time() < deadline:
            if loaded(page):
                print("app already awake: found 'BlastGuard'")
                browser.close()
                return 0
            btn = find_wake(page)
            if btn:
                print("app was asleep: clicking the wake button")
                btn.click()
                clicked = True
                break
            time.sleep(3)
        if not clicked:
            print("no wake button and no app text after 60s; waiting anyway")
        deadline = time.time() + 180
        while time.time() < deadline:
            if loaded(page):
                print("app loaded: found 'BlastGuard'")
                browser.close()
                return 0
            time.sleep(5)
        print("ERROR: the app never loaded (no 'BlastGuard' text after waiting)")
        dump_debug(page)
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
