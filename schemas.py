from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, le=1_000_000_000, max_digits=13, decimal_places=2)]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=6, decimal_places=3)]
GOALS = {
    "mortgage": "Nová hypotéka", "refinance": "Refinancovanie",
    "life": "Životné poistenie", "property": "Poistenie majetku",
    "invest": "Investovanie", "review": "Finančný prehľad",
}
DEBT_TYPES = {
    "mortgage": "Hypotéka", "consumer": "Spotrebný úver", "card": "Kreditná karta / prečerpanie",
    "lease": "Lízing", "other": "Iný záväzok",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Debt(StrictModel):
    id: str = Field(max_length=40)
    kind: Literal["mortgage", "consumer", "card", "lease", "other"]
    lender: str = Field(default="", max_length=100)
    balance: Money
    payment: Money
    rate: Rate
    limit: Money = Decimal("0")

    @model_validator(mode="after")
    def card_limit(self):
        if self.kind == "card" and self.limit < self.balance:
            raise ValueError("Limit kreditnej karty musí byť aspoň vo výške čerpania.")
        return self


class ClientData(StrictModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=30, pattern=r"^[+0-9 ()/-]+$")
    age: int = Field(ge=18, le=110)
    children: int = Field(ge=0, le=30)
    adults: int = Field(ge=1, le=10)
    income_employment: Money = Decimal("0")
    income_business: Money = Decimal("0")
    income_company: Money = Decimal("0")
    income_other: Money = Decimal("0")
    expenses: Money
    savings: Money = Decimal("0")
    debts: list[Debt] = Field(default_factory=list, max_length=30)
    goals: list[Literal["mortgage", "refinance", "life", "property", "invest", "review"]] = Field(min_length=1, max_length=6)
    requested_loan: Money = Decimal("0")
    requested_years: int = Field(default=30, ge=1, le=40)
    monthly_investment: Money = Decimal("0")
    notes: str = Field(default="", max_length=3000)
    privacy_acknowledged: Literal[True]
    ai_consent: bool = False

    @field_validator("goals")
    @classmethod
    def unique_goals(cls, value):
        return list(dict.fromkeys(value))


class Proposal(StrictModel):
    lender: str = Field(min_length=1, max_length=120)
    kind: Literal["mortgage", "refinance", "insurance", "investment", "review"]
    principal: Money = Decimal("0")
    annual_rate: Rate = Decimal("0")
    years: int = Field(default=30, ge=1, le=40)
    upfront_fees: Money = Decimal("0")
    monthly_costs: Money = Decimal("0")
    replace_ids: list[str] = Field(default_factory=list, max_length=30)
    living_minimum: Money | None = None
    assessed_payments: Money | None = None
    client_summary: str = Field(min_length=10, max_length=4000)
    documents: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def valid_loan(self):
        if self.kind in ("mortgage", "refinance") and self.principal <= 0:
            raise ValueError("Pri úvere vyplňte kladnú istinu.")
        if self.kind == "refinance" and not self.replace_ids:
            raise ValueError("Vyberte záväzky, ktoré sa majú refinancovať.")
        if self.kind not in ("mortgage", "refinance") and self.replace_ids:
            raise ValueError("Nahradenie záväzkov je dostupné iba pri úvere.")
        return self
