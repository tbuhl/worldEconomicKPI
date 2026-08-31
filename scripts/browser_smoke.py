"""Optional visual smoke test against a running local Streamlit server."""

from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def main() -> None:
    executable = next((path for path in CHROME_CANDIDATES if path.exists()), None)
    target = os.getenv("WORLD_KPI_URL", "http://localhost:8501")
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        launch_options = {"headless": True}
        if executable:
            launch_options["executable_path"] = str(executable)
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on(
            "console",
            lambda message: console_errors.append(message.text) if message.type == "error" else None,
        )
        page.goto(target, wait_until="domcontentloaded", timeout=45_000)
        main_panel = page.get_by_test_id("stMainBlockContainer")
        main_panel.get_by_role("heading", name="World KPI Radar", exact=True).wait_for(timeout=45_000)
        main_panel.get_by_role("heading", name="What the dashboard says now", exact=True).wait_for()
        page.screenshot(path=artifacts / "world-kpi-overview.png", full_page=True)

        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )

        checks: dict[str, bool | int] = {"overview": True, "horizontal_overflow_px": overflow}

        history_labels = page.get_by_text("Since 1990 · recommended", exact=True)
        history_label_count = history_labels.count()
        checks["full_history_default"] = any(
            history_labels.nth(index).is_visible() for index in range(history_label_count)
        )

        macro_tab = page.get_by_role("tab", name="Macro & policy", exact=True)
        macro_tab.click()
        main_panel.get_by_role("heading", name="Macro & policy", exact=True).wait_for()
        for marker in ("Dot-com peak", "GFC build-up", "Lehman"):
            labels = main_panel.get_by_text(marker, exact=True)
            label_count = labels.count()
            visible_labels = [labels.nth(index) for index in range(label_count) if labels.nth(index).is_visible()]
            checks[f"marker_{marker}"] = bool(visible_labels)
            if marker == "Dot-com peak" and visible_labels:
                visible_labels[0].scroll_into_view_if_needed()
        page.screenshot(path=artifacts / "world-kpi-long-history.png", full_page=False)

        destinations = {
            "Sovereign & rates": "Sovereign debt & the global rate anchor",
            "AI capital loop": "The AI capital loop",
            "KPI library": "KPI library & data dictionary",
        }
        for tab_name, heading in destinations.items():
            tab = page.get_by_role("tab", name=tab_name, exact=True)
            tab.click()
            main_panel.get_by_role("heading", name=heading, exact=True).wait_for()
            checks[tab_name] = tab.get_attribute("aria-selected") == "true"
            if tab_name == "Sovereign & rates":
                flow_heading = main_panel.get_by_role(
                    "heading", name="Who is buying, who is selling?", exact=True
                )
                flow_heading.wait_for()
                main_panel.get_by_text(
                    "Latest monthly net Treasury flow", exact=True
                ).wait_for()
                checks["top5_treasury_monitor"] = True
                page.screenshot(
                    path=artifacts / "world-kpi-foreign-holders.png", full_page=True
                )
                flow_heading.scroll_into_view_if_needed()
                page.screenshot(
                    path=artifacts / "world-kpi-foreign-holders-detail.png",
                    full_page=False,
                )
            if tab_name == "AI capital loop":
                page.screenshot(path=artifacts / "world-kpi-ai-loop.png", full_page=True)

        checks["console_errors"] = len(console_errors)
        if console_errors:
            checks["console_error_sample"] = console_errors[:5]

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.goto(target, wait_until="domcontentloaded", timeout=45_000)
        mobile.get_by_test_id("stMainBlockContainer").get_by_role(
            "heading", name="World KPI Radar", exact=True
        ).wait_for(timeout=45_000)
        mobile.get_by_test_id("stMainBlockContainer").get_by_role(
            "heading", name="What the dashboard says now", exact=True
        ).wait_for(timeout=45_000)
        checks["mobile_horizontal_overflow_px"] = mobile.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        mobile.screenshot(path=artifacts / "world-kpi-mobile.png", full_page=False)
        mobile.close()
        print(json.dumps(checks, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
