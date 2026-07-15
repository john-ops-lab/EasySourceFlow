"""Error types and JSON-safe error payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class EasySourceFlowError(Exception):
    code: str
    message: str
    next_steps: List[str]

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "next_steps": list(self.next_steps),
        }


def invalid_url(message: str) -> EasySourceFlowError:
    return EasySourceFlowError(
        code="invalid_url",
        message=message,
        next_steps=["Provide a valid public http or https URL."],
    )


def extraction_failed(message: str) -> EasySourceFlowError:
    return EasySourceFlowError(
        code="extraction_failed",
        message=message,
        next_steps=[
            "Open the link in a browser to confirm it is accessible.",
            "Try another public article URL.",
            "For restricted pages, provide copied article text in a future version.",
        ],
    )


def extraction_error(code: str, message: str, next_steps: List[str]) -> EasySourceFlowError:
    return EasySourceFlowError(code=code, message=message, next_steps=next_steps)


def dependency_missing(message: str) -> EasySourceFlowError:
    return EasySourceFlowError(
        code="dependency_missing",
        message=message,
        next_steps=[
            "Install the missing dependency in the project environment.",
            "Set the related EASYSOURCEFLOW_* path environment variable if it is installed elsewhere.",
            "Retry the same link after the dependency is available.",
        ],
    )


def need_cookies(message: str) -> EasySourceFlowError:
    return EasySourceFlowError(
        code="need_cookies",
        message=message,
        next_steps=[
            "Open the source in the local browser and confirm the account can access it.",
            "Import the platform login state from the EasySourceFlow Web maintenance page.",
            "Retry later if the platform is rate-limiting this machine.",
        ],
    )
