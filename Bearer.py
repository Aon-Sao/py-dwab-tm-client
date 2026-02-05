import datetime
import os
import pickle

import requests

from Types import BearerResult, ClientArgs, BearerFailure, TMError, BearerToken, BearerSuccess


class Bearer:
    def __init__(self, conn_str: str, conn_args: ClientArgs):
        self.conn_str = conn_str
        self.conn_args = conn_args
        self.token = None
        self.from_pickle = False

    def fetch_new(self) -> BearerResult:
        if hasattr((auth := self.conn_args.authorization_args.authorization), "getBearer"):
            return auth.getBearer()
        if auth.expiration_date < datetime.datetime.now(datetime.UTC):
            return BearerFailure(
                success=False,
                error=TMError.CredentialsExpired
            )

        def request_token() -> requests.Response:
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            params = {
                "client_id": auth.client_id,
                "client_secret": auth.client_secret,
                "grant_type": auth.grant_type
            }
            return requests.post(url=self.conn_str, headers=headers, params=params)

        if not (response := request_token()).ok:
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

            self.pickle_bearer(bearer)
            return BearerSuccess(
                success=True,
                token=bearer
            )

    @staticmethod
    def pickle_bearer(token: BearerToken):
        assert isinstance(token, BearerToken)
        with open("latest_bearer.pickle", 'wb') as fout:
            pickle.dump(token, fout, pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def unpickle_bearer() -> BearerToken | None:
        if os.path.exists("latest_bearer.pickle"):
            with open("latest_bearer.pickle", 'rb') as fin:
                if isinstance((obj := pickle.load(fin)), BearerToken):
                    return obj
                else:
                    Bearer.remove_pickle()
        return None

    @staticmethod
    def remove_pickle():
        if os.path.exists("latest_bearer.pickle"):
            os.remove("latest_bearer.pickle")

    def update_bearer(self) -> BearerResult:
        try:
            bearer_result = self.fetch_new()
            if not bearer_result.success:
                return bearer_result
            self.token = bearer_result.token
            self.from_pickle = False
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

    def is_viable(self, bearer: BearerToken | None = None) -> bool:
        if bearer is None:
            bearer = self.token
        if bearer is None:
            return False
        now = datetime.datetime.now(datetime.UTC)
        expiry = now + bearer.expires_in
        expired = expiry <= now
        expires_soon = bearer.expires_in < self.conn_args.bearer_margin
        return not (expired or expires_soon)

    def ensure(self) -> BearerResult:
        # If our in-memory bearer token is fine, return that
        if self.is_viable(self.token):
            return BearerSuccess(
                success=True,
                token=self.token
            )

        # If there is a local token, return that if it is valid,
        # delete it if it is not valid
        if (token := self.unpickle_bearer()) is not None:
            if not self.is_viable(token):
                self.remove_pickle()
            else:
                self.token = token
                self.from_pickle = True
                return BearerSuccess(
                    success=True,
                    token=token
                )

        # If we haven't found a viable token yet, get a new one
        return self.update_bearer()