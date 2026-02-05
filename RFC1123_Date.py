import datetime


class RFC1123Date:
    def __init__(self: RFC1123Date, date: datetime.datetime | str):
        if isinstance(date, datetime.datetime):
            self.datetime_obj: datetime.datetime = date
            self.datetime_str: str = self.utc_datetime_to_rfc1123_str(date)
        elif isinstance(date, str):
            self.datetime_str: str = date
            self.datetime_obj: datetime.datetime = self.rfc1123_str_to_utc_datetime(date)
        else:
            raise TypeError(f"date must be {datetime.datetime} or {str} not {type(date)}")

    def __str__(self: RFC1123Date) -> str:
        return self.datetime_str

    @staticmethod
    def utc_datetime_to_rfc1123_str(dt: datetime.datetime) -> str:
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    @staticmethod
    def rfc1123_str_to_utc_datetime(dt_str: str) -> datetime.datetime:
        fmt: str = "%a, %d %b %Y %H:%M:%S GMT"
        return datetime.datetime.strptime(dt_str, fmt)