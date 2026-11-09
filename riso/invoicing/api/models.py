"""Request and response models of the invoicing API."""

from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from riso.invoicing.application import SeriesView


class UsedNumberOut(BaseModel):
    number: str
    sequence: int
    kind: Literal["booked", "reserved", "external"] = Field(
        description="A booked invoice's; one kept for an unbooked invoice; or used outside riso"
    )
    invoice_id: str | None
    frozen: bool = Field(description="Never moves: exported, paid or used outside riso")


class NumberSeriesOut(BaseModel):
    series: str
    year: int
    pattern: str
    last_used: int = Field(description="The counter: the last sequence used")
    last_used_number: str | None
    next_number: str = Field(description="What the counter gives next")
    used: list[UsedNumberOut] = Field(description="The numbers held, lowest first")
    gaps: list[str] = Field(description="Free numbers between the lowest and the highest held")
    stored: bool = Field(description="False for a series of the year's list never used yet")

    @classmethod
    def of(cls, view: SeriesView) -> "NumberSeriesOut":
        return cls(
            series=view.series,
            year=view.year,
            pattern=view.pattern,
            last_used=view.last_used,
            last_used_number=view.last_used_number,
            next_number=view.next_number,
            used=[UsedNumberOut.model_validate(asdict(u)) for u in view.used],
            gaps=list(view.gaps),
            stored=view.stored,
        )


class NumberSeriesListOut(BaseModel):
    year: int
    items: list[NumberSeriesOut]


class LastUsedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_used: int = Field(ge=0, description="The new counter: the last sequence used")
