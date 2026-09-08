"""One-time interactive login to capture a Biwenger session token.

Opens a real Chrome window, waits for the user to log in manually, then reads
the session token and league/user ids from localStorage and writes config.json.
"""
import json
import time

from playwright.sync_api import sync_playwright

CONFIG_PATH = "config.json"
LOGIN_URL = "https://biwenger.as.com/"
POLL_SECONDS = 2
TIMEOUT_SECONDS = 300


def wait_for_login(page):
    waited = 0
    while waited < TIMEOUT_SECONDS:
        token = page.evaluate("localStorage.getItem('satellizer_token')")
        if token:
            return token
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
    raise TimeoutError("No se detecto login tras 5 minutos. Vuelve a ejecutar el script.")


def pick_league(leagues):
    if len(leagues) == 1:
        return leagues[0]
    print("Tienes varias ligas, elige una:")
    for index, league in enumerate(leagues):
        print(f"  [{index}] {league['name']} (id {league['id']})")
    choice = int(input("Numero de liga: "))
    return leagues[choice]


def main():
    with sync_playwright() as playwright:
        # Use the real, installed Google Chrome (not Playwright's bundled Chromium) and
        # disable the "AutomationControlled" flag: Google's login blocks OAuth (e.g.
        # "Iniciar sesion con Google") from browsers it detects as automated otherwise,
        # even for a real personal login.
        browser = playwright.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page()
        page.goto(LOGIN_URL)
        print("Inicia sesion en la ventana de Chrome. Esperando...")
        token = wait_for_login(page)

        last_session = json.loads(page.evaluate("localStorage.getItem('lastSession')"))
        league = pick_league(last_session["leagues"])

        config = {
            "token": token,
            "league_id": league["id"],
            "user_id": league["user"]["id"],
            "league_name": league["name"],
        }
        with open(CONFIG_PATH, "w") as config_file:
            json.dump(config, config_file, indent=2)

        print(f"Listo. Guardado en {CONFIG_PATH} para la liga '{league['name']}'.")
        browser.close()


if __name__ == "__main__":
    main()
