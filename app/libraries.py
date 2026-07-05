"""Reference libraries injected into negotiation agent context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NegotiationLibrary:
    id: str
    name: str
    description: str
    locale: str
    context: str


NEGOTIATION_LIBRARIES: tuple[NegotiationLibrary, ...] = (
    NegotiationLibrary(
        id="takdin-legal",
        name="תקדין — Israeli legal context",
        description=(
            "Israeli contract and dispute norms: good faith, reasonableness, "
            "limitation periods, and settlement framing."
        ),
        locale="he",
        context="""Reference library — Israeli legal negotiation norms (public legal principles, not live case lookup):

- חובת תום לב (good faith): parties must negotiate honestly; hidden bad faith weakens enforceability.
- סבירות (reasonableness): courts ask whether terms are reasonable for the situation and power balance.
- הסכם מכוח חוק / חוזים: written terms matter; vague clauses are interpreted against the drafter when ambiguous.
- פשרה וגישור: settlement before litigation is expected; offers should leave room for mediated compromise.
- תקופות התיישנות: time limits apply — urgency can be a legitimate negotiation lever when documented.
- נזק ופיצוי: quantify damages concretely (amounts, dates, scope) rather than vague threats.
- סודיות: settlement and NDA clauses are common trade-offs in commercial disputes.
- When citing law, prefer specific sections and concrete numbers; avoid inventing case names or docket numbers.""",
    ),
    NegotiationLibrary(
        id="contract-clauses",
        name="Contract clauses",
        description="Standard commercial terms agents can propose, counter, or trade off.",
        locale="en",
        context="""Reference library — common negotiable contract terms:

- Price / payment schedule (net-30, milestones, late fees)
- Scope of work and acceptance criteria
- Term and termination (notice period, cause vs convenience)
- Liability cap and excluded damages
- Indemnification scope
- IP ownership and license grants
- Confidentiality and data handling
- Governing law and dispute resolution (court vs arbitration)
- Force majeure and change control
Agents should attach numbers, dates, and explicit trade-offs when using these terms.""",
    ),
    NegotiationLibrary(
        id="salary-hr",
        name="Salary & HR",
        description="Employment offer negotiation: base, bonus, equity, benefits, start date.",
        locale="en",
        context="""Reference library — employment negotiation levers:

- Base salary and currency
- Signing bonus vs performance bonus
- Equity / options vesting schedule
- Title, level, and review timeline
- Remote / hybrid / relocation
- Vacation, sick leave, parental leave
- Non-compete and notice period (jurisdiction-dependent)
- Start date and probation period
Use specific figures and dates; bundle concessions (give X to get Y).""",
    ),
)

_LIBRARY_BY_ID = {lib.id: lib for lib in NEGOTIATION_LIBRARIES}


def list_libraries() -> list[dict[str, str]]:
    return [
        {
            "id": lib.id,
            "name": lib.name,
            "description": lib.description,
            "locale": lib.locale,
        }
        for lib in NEGOTIATION_LIBRARIES
    ]


def resolve_libraries(
    library_ids: list[str] | None = None,
    extra_context: str | None = None,
) -> tuple[list[str], str]:
    ids = [item.strip() for item in (library_ids or []) if item.strip()]
    sections: list[str] = []

    for lib_id in ids:
        lib = _LIBRARY_BY_ID.get(lib_id)
        if lib:
            sections.append(f"### {lib.name}\n{lib.context}")

    custom = (extra_context or "").strip()
    if custom:
        sections.append(f"### Custom reference\n{custom}")

    if not sections:
        return ids, ""

    brief = (
        "Reference libraries (use when relevant; do not invent citations outside this material):\n\n"
        + "\n\n".join(sections)
    )
    return ids, brief
