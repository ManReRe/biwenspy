"""Thin HTTP client for the internal Biwenger API."""
import requests

BASE_URL = "https://biwenger.as.com/api/v2"


class BiwengerAuthError(Exception):
    """Raised when the API rejects the stored token (HTTP 401)."""


class BiwengerClient:
    def __init__(self, token, league_id, user_id, base_url=BASE_URL, session=None):
        self.token = token
        self.league_id = league_id
        self.user_id = user_id
        self.base_url = base_url
        self.session = session or requests.Session()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-League": str(self.league_id),
            "X-User": str(self.user_id),
            "X-Lang": "es",
            "X-Version": "665",
        }

    def _get(self, path, params=None):
        response = self.session.get(
            f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=15
        )
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

    def get_players(self):
        data = self._get("/competitions/la-liga/data", params={"lang": "es", "score": "5"})
        teams = {int(team_id): info.get("name") for team_id, info in data.get("teams", {}).items()}
        players = {}
        for player_id, info in data.get("players", {}).items():
            players[int(player_id)] = {
                "name": info.get("name"),
                "team": teams.get(info.get("teamID")),
            }
        return players
