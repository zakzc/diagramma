"""One error shape for the whole API: {"error": {"code", "message"}} (SPEC §5.2)."""


class AppError(Exception):
    def __init__(self, code: str, message: str):
        # Both args go to Exception so the error survives pickling across processes.
        super().__init__(code, message)
        self.code = code
        self.message = message


STATUS_BY_CODE = {
    "INVALID_URL": 400,
    "REPO_NOT_FOUND": 404,
    "AUTH_REQUIRED": 401,
    "CLONE_FAILED": 502,
    "NOTHING_DETECTED": 422,
    "JOB_NOT_FOUND": 404,
    "DIAGRAM_NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
}
