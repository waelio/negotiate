/**
 * Reference libraries injected into agent prompts during negotiation.
 * Each library adds domain context both agents may cite when making offers.
 */

export interface NegotiationLibrary {
  id: string;
  name: string;
  description: string;
  locale: string;
  context: string;
}

export const NEGOTIATION_LIBRARIES: NegotiationLibrary[] = [
  {
    id: "takdin-legal",
    name: "תקדין — Israeli legal context",
    description:
      "Israeli contract and dispute norms: good faith, reasonableness, limitation periods, and settlement framing.",
    locale: "he",
    context: `Reference library — Israeli legal negotiation norms (public legal principles, not live case lookup):

- חובת תום לב (good faith): parties must negotiate honestly; hidden bad faith weakens enforceability.
- סבירות (reasonableness): courts ask whether terms are reasonable for the situation and power balance.
- הסכם מכוח חוק / חוזים: written terms matter; vague clauses are interpreted against the drafter when ambiguous.
- פשרה וגישור: settlement before litigation is expected; offers should leave room for mediated compromise.
- תקופות התיישנות: time limits apply — urgency can be a legitimate negotiation lever when documented.
- נזק ופיצוי: quantify damages concretely (amounts, dates, scope) rather than vague threats.
- סודיות: settlement and NDA clauses are common trade-offs in commercial disputes.
- When citing law, prefer specific sections and concrete numbers; avoid inventing case names or docket numbers.`,
  },
  {
    id: "contract-clauses",
    name: "Contract clauses",
    description: "Standard commercial terms agents can propose, counter, or trade off.",
    locale: "en",
    context: `Reference library — common negotiable contract terms:

- Price / payment schedule (net-30, milestones, late fees)
- Scope of work and acceptance criteria
- Term and termination (notice period, cause vs convenience)
- Liability cap and excluded damages
- Indemnification scope
- IP ownership and license grants
- Confidentiality and data handling
- Governing law and dispute resolution (court vs arbitration)
- Force majeure and change control
Agents should attach numbers, dates, and explicit trade-offs when using these terms.`,
  },
  {
    id: "salary-hr",
    name: "Salary & HR",
    description: "Employment offer negotiation: base, bonus, equity, benefits, start date.",
    locale: "en",
    context: `Reference library — employment negotiation levers:

- Base salary and currency
- Signing bonus vs performance bonus
- Equity / options vesting schedule
- Title, level, and review timeline
- Remote / hybrid / relocation
- Vacation, sick leave, parental leave
- Non-compete and notice period (jurisdiction-dependent)
- Start date and probation period
Use specific figures and dates; bundle concessions (give X to get Y).`,
  },
];

const libraryById = new Map(NEGOTIATION_LIBRARIES.map((lib) => [lib.id, lib]));

export function listLibraries(): Array<Pick<NegotiationLibrary, "id" | "name" | "description" | "locale">> {
  return NEGOTIATION_LIBRARIES.map(({ id, name, description, locale }) => ({
    id,
    name,
    description,
    locale,
  }));
}

export function resolveLibraries(
  libraryIds?: string[],
  extraContext?: string
): { ids: string[]; brief: string } {
  const ids = (libraryIds ?? []).map((id) => id.trim()).filter(Boolean);
  const sections: string[] = [];

  for (const id of ids) {
    const lib = libraryById.get(id);
    if (lib) {
      sections.push(`### ${lib.name}\n${lib.context}`);
    }
  }

  const custom = extraContext?.trim();
  if (custom) {
    sections.push(`### Custom reference\n${custom}`);
  }

  if (sections.length === 0) {
    return { ids, brief: "" };
  }

  return {
    ids,
    brief: `Reference libraries (use when relevant; do not invent citations outside this material):\n\n${sections.join("\n\n")}`,
  };
}
