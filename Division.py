from Types import DivisionData, APIResult, numeric, generic_to_string


class Division:
    def __init__(self: Division, client, data: DivisionData):
        self.id: numeric = data.id
        self.name: str = data.name
        self.client = client  # of type Client, not imported to prevent circular imports

    def __str__(*args, indent="", **kwargs):
        return generic_to_string(*args, **kwargs, ignored_fields=["client"])

    def get_teams(self: Division) -> APIResult:
        rs: APIResult = self.client.get(f"/api/teams/{self.id}")
        if rs.success:
            rs.data = rs.data["teams"]
        return rs

    def get_matches(self: Division) -> APIResult:
        rs: APIResult = self.client.get(f"/api/matches/{self.id}")
        if rs.success:
            rs.data = rs.data["matches"]
        return rs

    def get_rankings(self: Division, _round: int) -> APIResult:
        rs: APIResult = self.client.get(f"/api/rankings/{self.id}/{_round}")
        if rs.success:
            rs.data = rs.data["rankings"]
        return rs
