import datetime


class RFC1123Date:
    def __init__(self, date: datetime.datetime | str):
        if isinstance(date, datetime.datetime):
            self.datetime_obj = date
            self.datetime_str = self.utc_datetime_to_rfc1123_str(date)
        elif isinstance(date, str):
            self.datetime_str = date
            self.datetime_obj = self.rfc1123_str_to_utc_datetime(date)
        else:
            raise TypeError(f"date must be {datetime.datetime} or {str} not {type(date)}")

    def __str__(self):
        return self.datetime_str

    @staticmethod
    def utc_datetime_to_rfc1123_str(dt):
        return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    @staticmethod
    def rfc1123_str_to_utc_datetime(dt_str):
        fmt = "%a, %d %b %Y %H:%M:%S GMT"
        return datetime.datetime.strptime(dt_str, fmt)