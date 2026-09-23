"""统一错误结构（m0-plan §2.1.1）。

所有非 2xx 响应体（顶层即为 error，不做 detail 包装）：
    {"error": {"code": "...", "message": "...", "details": {...}|null}}
code 为 SCREAMING_SNAKE_CASE 全集枚举（openapi.yaml 契约）。

用自定义异常而非 FastAPI HTTPException（后者强制包一层 {"detail": ...}），
由 main.py 注册的 exception_handler 输出裸 body。
"""
from __future__ import annotations

from starlette import status


class ApiError(Exception):
    """带契约错误结构的业务异常。detail 即最终响应体的错误对象。"""

    def __init__(self, code: str, message: str, details: object | None = None,
                 http: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.http = http

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message,
                          "details": self.details}}


def err(code: str, message: str, details: object | None = None,
        http: int = status.HTTP_400_BAD_REQUEST) -> ApiError:
    return ApiError(code, message, details, http)


def not_found(resource: str, rid: object) -> ApiError:
    return ApiError("NOT_FOUND", f"{resource} {rid} 不存在",
                    {"resource": resource, "id": rid},
                    http=status.HTTP_404_NOT_FOUND)


def validation_failed(errors: list) -> ApiError:
    return ApiError("VALIDATION_FAILED", "字段级校验失败", {"errors": errors},
                    http=status.HTTP_422_UNPROCESSABLE_CONTENT)


INTERNAL_ERROR = ApiError("INTERNAL_ERROR", "服务端异常",
                          http=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 兼容旧别名（路由沿用大写风格，避免大面积改动）。
NOT_FOUND = not_found
VALIDATION_FAILED = validation_failed