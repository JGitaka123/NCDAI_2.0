"""Account lifecycle payloads; passwords retain intentional whitespace."""
from typing import Annotated
from pydantic import Field, StrictBool, StringConstraints, model_validator
from .schemas import StrictModel

PasswordText = Annotated[str, StringConstraints(strip_whitespace=False, strict=True)]


class PasswordChange(StrictModel):
    current_password: PasswordText = Field(min_length=1, max_length=256)
    new_password: PasswordText = Field(min_length=14, max_length=256)

    @model_validator(mode="after")
    def different_nonempty_password(self):
        if not self.new_password.strip():
            raise ValueError("The new password cannot consist only of whitespace")
        if self.new_password == self.current_password:
            raise ValueError("Choose a new password different from the current password")
        return self


class AccountStatusChange(StrictModel):
    active: StrictBool
