from playwright.sync_api import sync_playwright
import os

def take_screenshot():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # Use localhost since it's in the same container
        page.goto("http://localhost:3000/configure")
        page.wait_for_load_state("networkidle")

        # Take a full page screenshot
        os.makedirs("/home/jules/verification", exist_ok=True)
        page.screenshot(path="/home/jules/verification/config_page.png", full_page=True)
        print("Screenshot saved to /home/jules/verification/config_page.png")
        browser.close()

if __name__ == "__main__":
    take_screenshot()
