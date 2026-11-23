class UserError(Exception):
    """A problem with the upload that the user can fix. The message is shown on the site."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class NotReadyError(Exception):
    """Models are still loading or the startup check failed."""
