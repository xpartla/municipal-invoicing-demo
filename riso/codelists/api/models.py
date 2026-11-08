"""Request and response models of the codelists API."""

from pydantic import BaseModel

from riso.codelists.domain import HealthCode, HealthFinding, HealthSeverity, ListKind


class HealthFindingOut(BaseModel):
    code: HealthCode
    severity: HealthSeverity
    subject: str
    where: str | None
    kind: ListKind | None
    count: int
    message: str

    @classmethod
    def of(cls, finding: HealthFinding) -> "HealthFindingOut":
        return cls(
            code=finding.code,
            severity=finding.severity,
            subject=finding.subject,
            where=finding.where,
            kind=finding.kind,
            count=finding.count,
            message=finding.message,
        )


class HealthReportOut(BaseModel):
    year: int
    errors: int
    warnings: int
    findings: list[HealthFindingOut]

    @classmethod
    def of(cls, year: int, findings: list[HealthFinding]) -> "HealthReportOut":
        return cls(
            year=year,
            errors=sum(f.severity is HealthSeverity.ERROR for f in findings),
            warnings=sum(f.severity is HealthSeverity.WARNING for f in findings),
            findings=[HealthFindingOut.of(f) for f in findings],
        )
