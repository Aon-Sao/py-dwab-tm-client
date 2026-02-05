from Types import *
from Fieldset import Fieldset
from Division import Division

from urllib.parse import urlparse, urljoin

import hmac
import json
import os.path
import pickle
import requests
import datetime


class Client:
    connection_args: ClientArgs
    bearer_token: BearerToken | None = None
    connection_string = "https://auth.vextm.dwabtech.com/oauth2/token"
    endpoint_cache: dict[str, EndpointCacheMember] = dict()

    def __init__(self, args: ClientArgs):
        self.connection_args = args
        # Could be useful information if there are errors
        self.bearer_from_pickle = False

    def _get_bearer(self) -> BearerResult:
        if hasattr((auth := self.connection_args.authorization_args.authorization), "getBearer"):
            return auth.getBearer()
        if auth.expiration_date < datetime.datetime.now(datetime.UTC):
            return BearerFailure(
                success=False,
                error=TMError.CredentialsExpired
            )

        def request_bearer() -> requests.Response:
            print(f"DEBUG: client is requesting a new bearer")
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            params = {
                "client_id": auth.client_id,
                "client_secret": auth.client_secret,
                "grant_type": auth.grant_type
            }
            return requests.post(url=self.connection_string, headers=headers, params=params)

        if not (response := request_bearer()).ok:
            if response.json()["error"] == "invalid_client":
                return BearerFailure(
                    success=False,
                    error=TMError.CredentialsInvalid
                )
            else:
                return BearerFailure(
                    success=False,
                    error=TMError.CredentialsError
                )
        else:
            bearer = BearerToken(
                access_token=response.json()["access_token"],
                token_type=response.json()["token_type"],
                # Assuming number of seconds
                expires_in=datetime.timedelta(seconds=float(response.json()["expires_in"]))
            )

        self._pickle_bearer(bearer)
        return BearerSuccess(
            success=True,
            token=bearer
        )


    @staticmethod
    def _pickle_bearer(token: BearerToken):
        assert isinstance(token, BearerToken)
        with open("latest_bearer.pickle", 'wb') as fout:
            pickle.dump(token, fout, pickle.HIGHEST_PROTOCOL)
        with open("latest_bearer.json", 'w') as fout:
            json.dump({
                "access_token": token.access_token,
                "token_type": token.token_type,
                "expires_in": token.expires_in.seconds
            }, fout)

    @staticmethod
    def _unpickle_bearer() -> BearerToken | None:
        if os.path.exists("latest_bearer.pickle"):
            with open("latest_bearer.pickle", 'rb') as fin:
                if isinstance((obj := pickle.load(fin)), BearerToken):
                    return obj
                else:
                    Client._remove_pickle()
        return None

    @staticmethod
    def _remove_pickle():
        if os.path.exists("latest_bearer.pickle"):
            os.remove("latest_bearer.pickle")
        if os.path.exists("latest_bearer.json"):
            os.remove("latest_bearer.json")

    def _update_bearer(self) -> BearerResult:
        try:
            bearer_result = self._get_bearer()
            if not bearer_result.success:
                return bearer_result
            self.bearer_token = bearer_result.token
            self.bearer_from_pickle = False
            return BearerSuccess(
                success=True,
                token=bearer_result.token
            )
        except Exception as e:
            return BearerFailure(
                success=False,
                error=TMError.CredentialsError,
                error_details=e
            )

    def _bearer_is_viable(self, bearer: BearerToken | None = None) -> bool:
        if bearer is None:
            bearer = self.bearer_token
        if bearer is None:
            return False
        expiry = datetime.datetime.now() + bearer.expires_in
        bearer_is_expired  = expiry <= datetime.datetime.now()
        bearer_expires_soon = bearer.expires_in < self.connection_args.bearer_margin
        return not (bearer_is_expired or bearer_expires_soon)

    def ensure_bearer(self):
        # If our in-memory bearer token is fine, return that
        if self._bearer_is_viable(self.bearer_token):
            return BearerSuccess(
                success=True,
                token=self.bearer_token
            )

        # If there is a local token, return that if it is valid,
        # delete it if it is not valid
        if (bearer_token := self._unpickle_bearer()) is not None:
            if not self._bearer_is_viable(bearer_token):
                self._remove_pickle()
            else:
                self.bearer_token = bearer_token
                self.bearer_from_pickle = True
                return BearerSuccess(
                    success=True,
                    token=bearer_token
                )

        # If we haven't found a viable token yet, get a new one
        return self._update_bearer()

    def get_divisions(self) -> APIResult:
        if not (rs:=self.get("/api/divisions")).success:
            return rs
        data = [DivisionData(id=div["id"], name=div["name"]) for div in rs.data["divisions"]]
        data = [Division(self, div_dat) for div_dat in data]
        return APISuccess(
            success=rs.success,
            data=data,
            cached=rs.cached
        )

    def get_fieldsets(self) -> APIResult:
        if not (rs:=self.get("/api/fieldsets")).success:
            return rs
        data = [FieldsetData(id=div["id"], name=div["name"]) for div in rs.data["fieldSets"]]
        data = [Fieldset(self, fs_data) for fs_data in data]
        return APISuccess(
            success=rs.success,
            data=data,
            cached=rs.cached
        )

    def get_teams(self) -> APIResult:
        return self.get("/api/teams")

    def get_skills(self) -> APIResult:
        return self.get("/api/skills")

    def get_event_info(self) -> APIResult:
        return self.get("/api/event")

    @staticmethod
    def utc_datetime_to_rfc1123_str(dt):
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    @staticmethod
    def rfc1123_str_to_utc_datetime(dt_str):
        fmt = "%a, %d %b %Y %H:%M:%S GMT"
        return datetime.datetime.strptime(dt_str, fmt)

    def get_authorization_headers(self, url, method = "GET") -> dict:
        # TM dates look like "Wed, 04 Feb 2026 06:48:25 GMT"
        tm_date = self.utc_datetime_to_rfc1123_str(datetime.datetime.now(datetime.timezone.utc))

        parsed_url = urlparse(url)

        string_to_sign = "\n".join([
            method,
            parsed_url.path + parsed_url.query,
            f"token:{self.bearer_token.access_token}",
            f"host:{parsed_url.netloc}",
            f"x-tm-date:{tm_date}"
        ])
        string_to_sign += "\n"

        signature = hmac.new(key=self.connection_args.clientAPIKey.encode("UTF-8"), digestmod="sha256")
        signature.update(string_to_sign.encode("UTF-8"))
        signature = signature.hexdigest()

        return {
            "Authorization": f"Bearer {self.bearer_token.access_token}",
            "x-tm-date": f"{tm_date}",
            "x-tm-signature": f"{signature}",
            "Host": f"{parsed_url.netloc}"
        }

    def connect(self) -> ConnectionResult:
        if not (rs:=self.ensure_bearer()).success:
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
        if not (rs:=self.ensure_bearer()).success:
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
                headers |= { "If-Modified-Since": self.utc_datetime_to_rfc1123_str(last_modified) }

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
                            last_modified=self.rfc1123_str_to_utc_datetime(response.headers.get("Last-Modified"))
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