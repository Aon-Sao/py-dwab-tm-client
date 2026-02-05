from Types import *
from Bearer import Bearer
from RFC1123_Date import RFC1123Date
from Fieldset import Fieldset
from Division import Division

from urllib.parse import urlparse, urljoin

import hmac
import requests
import datetime


class Client:
    connection_string = "https://auth.vextm.dwabtech.com/oauth2/token"

    def __init__(self, args: ClientArgs):
        self.connection_args: ClientArgs = args
        self.endpoint_cache: dict[str, EndpointCacheMember] = dict()
        self.bearer: Bearer | None = None

    def get_divisions(self) -> APIResult:
        if not (rs:=self.get("/api/divisions")).success:
            return rs
        data = [DivisionData(id=div["id"], name=div["name"]) for div in rs.data["divisions"]]
        data = [Division(self, div_dat) for div_dat in data]
        return APISuccess(
            success=True,
            data=data,
            cached=rs.cached
        )

    def get_fieldsets(self) -> APIResult:
        if not (rs:=self.get("/api/fieldsets")).success:
            return rs
        data = [FieldsetData(id=div["id"], name=div["name"]) for div in rs.data["fieldSets"]]
        data = [Fieldset(self, fs_data) for fs_data in data]
        return APISuccess(
            success=True,
            data=data,
            cached=rs.cached
        )

    def get_teams(self) -> APIResult:
        return self.get("/api/teams")

    def get_skills(self) -> APIResult:
        return self.get("/api/skills")

    def get_event_info(self) -> APIResult:
        return self.get("/api/event")


    def get_authorization_headers(self, url, method = "GET") -> dict:
        # TM dates look like "Wed, 04 Feb 2026 06:48:25 GMT"
        tm_date = str(RFC1123Date(datetime.datetime.now(datetime.timezone.utc)))

        parsed_url = urlparse(url)

        string_to_sign = "\n".join([
            method,
            parsed_url.path + parsed_url.query,
            f"token:{self.bearer.token.access_token}",
            f"host:{parsed_url.netloc}",
            f"x-tm-date:{tm_date}"
        ])
        string_to_sign += "\n"

        signature = hmac.new(key=self.connection_args.clientAPIKey.encode("UTF-8"), digestmod="sha256")
        signature.update(string_to_sign.encode("UTF-8"))
        signature = signature.hexdigest()

        return {
            "Authorization": f"Bearer {self.bearer.token.access_token}",
            "x-tm-date": f"{tm_date}",
            "x-tm-signature": f"{signature}",
            "Host": f"{parsed_url.netloc}"
        }

    def connect(self) -> ConnectionResult:
        if not (rs:=self.bearer.ensure()).success:
            return ConnectionFailure(
                success=False,
                origin="bearer",
                error=rs.error,
                error_details=rs.error_details
            )

        if not (div_rs := self.get_divisions()).success:
            return ConnectionFailure(
                success=False,
                origin="connection",
                error=div_rs.error,
                error_details=div_rs.error_details
            )

        if not (fs_rs:=self.get_fieldsets()).success:
            return ConnectionFailure(
                success=False,
                origin="connection",
                error=fs_rs.error,
                error_details=fs_rs.error_details
            )

        return ConnectionSuccess(
            success=True
        )

    def get(self, path: str) -> APIResult:
        if not (rs:=self.bearer.ensure()).success:
            return APIFailure(
                success=False,
                error=rs.error
            )

        url = urljoin(self.connection_args.address, path)
        headers = { "Content-Type": "application/json" }

        try:
            headers |= self.get_authorization_headers(url, "GET",)
            if str(url) in self.endpoint_cache.keys():
                last_modified = self.endpoint_cache[str(url)].last_modified
                headers |= { "If-Modified-Since": str(RFC1123Date(last_modified)) }

            response = requests.get(url, headers=headers)

            match response.status_code:
                case 503:
                    return APIFailure(
                        success=False,
                        error=TMError.WebServerNotEnabled,
                        error_details=response.json()
                    )
                case 401:
                    return APIFailure(
                        success=False,
                        error=TMError.WebServerInvalidSignature,
                        error_details=response.json()
                    )
                case 304:
                    return APISuccess(
                        success=True,
                        data=self.endpoint_cache[str(url)].data,
                        cached=True
                    )
                case 200:
                    # Update the endpoint cache
                    if "Last-Modified" in response.headers.keys():
                        self.endpoint_cache[str(url)] = EndpointCacheMember(
                            data=response.json(),
                            last_modified=RFC1123Date(response.headers.get("Last-Modified")).datetime_obj
                        )
                    return APISuccess(
                        success=True,
                        data=response.json(),
                        cached=False
                    )
                case _:
                    return APIFailure(
                        success=False,
                        error=TMError.WebSocketError,
                        error_details=response.json()
                    )

        except Exception as e:
            return APIFailure(
                success=False,
                error=TMError.WebServerConnectionError,
                error_details=e
            )