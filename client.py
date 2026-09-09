"""Thin HTTP client for the internal Biwenger API."""
import requests
from tenacity import retry, retry_if_exception_type, retry_if_result, stop_after_attempt, wait_exponential

BASE_URL = "https://biwenger.as.com/api/v2"

# A real-browser User-Agent (plus Origin/Referer): Biwenger sits behind Cloudflare,
# which can 403 requests that look like a bare python-requests client even when the
# token/headers are otherwise valid.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://biwenger.as.com",
    "Referer": "https://biwenger.as.com/",
}


class BiwengerAuthError(Exception):
    """Raised when the API rejects the stored token (HTTP 401)."""


def _is_server_error(response):
    return response.status_code >= 500


class BiwengerClient:
    def __init__(self, token, league_id, user_id, base_url=BASE_URL, session=None):
        self.token = token
        self.league_id = league_id
        self.user_id = user_id
        self.base_url = base_url
        self.session = session or requests.Session()

    def _headers(self):
        return {
            **BROWSER_HEADERS,
            "Authorization": f"Bearer {self.token}",
            "X-League": str(self.league_id),
            "X-User": str(self.user_id),
            "X-Lang": "es",
            "X-Version": "665",
        }

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=(
            retry_if_exception_type((requests.ConnectionError, requests.Timeout))
            | retry_if_result(_is_server_error)
        ),
    )
    def _request(self, path, params):
        return self.session.get(
            f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=15
        )

    def _get(self, path, params=None):
        # Transient network errors and 5xx responses are retried (with backoff) inside
        # _request; a 401 means the token itself is bad, so it fails fast instead.
        response = self._request(path, params)
        if response.status_code == 401:
            raise BiwengerAuthError(
                "Biwenger rechazo el token (401). Vuelve a ejecutar capture_token.py."
            )
        response.raise_for_status()
        return response.json()["data"]

    def get_league_users(self):
        return self._get(f"/league/{self.league_id}")["users"]

    def get_standings(self):
        return self._get(f"/league/{self.league_id}", params={"fields": "standings"})["standings"]

    def get_board_page(self, offset, limit=500):
        return self._get(f"/league/{self.league_id}/board", params={"offset": offset, "limit": limit})

    def get_own_balance(self):
        """Return the logged-in user's real current balance for this league, or
        None if it can't be determined (e.g. the account has left the league).

        This is the one balance figure the API exposes directly even when the
        league's "balance" privacy setting is "hidden" (that setting only hides
        *other* managers' balances) -- used to calibrate the reconstructed
        balance timeline against reality, since season transitions can reset
        budgets in ways the board's event log doesn't capture.
        """
        data = self._get("/account")
        for league in data.get("leagues", []):
            if league.get("id") == self.league_id:
                return league.get("user", {}).get("balance")
        return None

    def get_players(self):
        data = self._get("/competitions/la-liga/data", params={"lang": "es", "score": "5"})
        teams = {int(team_id): info.get("name") for team_id, info in data.get("teams", {}).items()}
        players = {}
        for player_id, info in data.get("players", {}).items():
            players[int(player_id)] = {
                "name": info.get("name"),
                "team": teams.get(info.get("teamID")),
                "position": info.get("position"),
                "status": info.get("status", "ok"),
                # Points from the player's most recently played rounds, oldest first.
                "recent_points": info.get("fitness") or [],
            }
        return players

    def get_manager_squad(self, user_id):
        """Return the current squad of any manager in the league (not just self):
        [{"player_id", "price_paid", "acquired_date"}, ...].

        Confirmed live: /user/{id} exposes any manager's owned players even when
        the league hides balances, since that privacy setting only affects money.
        `price` is absent for players kept from before the tracked purchase
        history (e.g. season start), so price_paid can be None.
        """
        data = self._get(f"/user/{user_id}", params={"fields": "*,players(id,owner)"})
        squad = []
        for entry in data.get("players", []):
            owner = entry.get("owner") or {}
            squad.append({
                "player_id": entry["id"],
                "price_paid": owner.get("price"),
                "acquired_date": owner.get("date"),
            })
        return squad
