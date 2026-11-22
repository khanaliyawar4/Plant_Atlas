from __future__ import annotations

GATE_SYSTEM = """\
You are a strict triage classifier for biology papers. You return ONLY a
single JSON object. No prose, no markdown fences, no explanation.

Decide whether the article excerpt is BOTH:
  (a) a PRIMARY RESEARCH article — i.e. it presents original experimental
      results. Reviews, mini-reviews, perspectives, opinions, commentaries,
      editorials, news pieces, and protocol-only papers are NOT primary
      research.
  (b) reports PLANT BIOENGINEERING work — i.e. one or more genes are
      overexpressed, knocked out, knocked down, edited (CRISPR/TALEN/ZFN),
      silenced (RNAi/amiRNA), or otherwise modified IN a plant species, and
      the paper measures the resulting effect on the plant.

Return:
  {"qualifies": true,  "reason": "<=200 chars"}     // both (a) and (b) hold
  {"qualifies": false, "reason": "<=200 chars"}     // otherwise

The reason is for human auditing. Keep it short and concrete.
"""

GATE_USER_TEMPLATE = """\
PMCID: {pmcid}
DOI:   {doi}
ARTICLE TYPE (front-matter, if any): {article_type}

--- BODY EXCERPT (first ~6000 chars; may be truncated) ---
{body_excerpt}
--- END EXCERPT ---

Return your JSON now.
"""

def build_gate_messages(pmcid: str, doi: str | None,
                         article_type: str | None, body: str) -> list[dict]:
    excerpt = body[:6000]
    user = GATE_USER_TEMPLATE.format(
        pmcid=pmcid,
        doi=doi or "(none found)",
        article_type=article_type or "(unknown)",
        body_excerpt=excerpt,
    )
    return [
        {"role": "system", "content": GATE_SYSTEM},
        {"role": "user",   "content": user},
    ]

EXTRACT_SYSTEM = """\
You are an expert plant-bioengineering curator. Given the main body of a
primary research article, you extract every DNA construct used to engineer
a plant species in that paper, and for each construct emit one row of a
structured 10-field record.

CRITICAL OUTPUT RULES — read carefully:

  * Return ONLY a JSON object with one top-level field "rows".
  * Return an empty rows list ({"rows": []}) if the paper is NOT plant
    bioengineering, if you find no construct, or if you cannot ground the
    extraction in verbatim text from the body. NEVER invent rows.
  * If a field is genuinely unknown from the text, use the exact string
    "NA" — do NOT guess. (Exception: "evidence_quote" must always be a
    real verbatim quote; if you have no quote, omit the row entirely.)
  * Tabs and newlines inside string values are forbidden; use spaces.
  * The 9 published fields plus the evidence_quote are described below;
    the JSON schema is enforced by the runtime, so emit valid types.

The 10 fields per row, in this order:

1. "plant_species"      — Latin binomial, e.g. "Arabidopsis thaliana".
                          If multiple species are engineered with the SAME
                          construct, list them comma-separated.

2. "genes"              — formatted EXACTLY as:
                          gene1 (name, definition, source), gene2 (name, definition, source), ...
                          where:
                            * name       = the gene symbol/identifier the paper uses
                            * definition = a short functional description from the paper
                            * source     = the organism/source of the gene (e.g. "Arabidopsis
                                            thaliana", "Escherichia coli", "synthetic")
                          If only one gene, still use this template with one entry.

3. "modification_type"  — one of: "overexpression", "knockout", "knockdown",
                          "gene editing (CRISPR)", "RNAi", "amiRNA",
                          "complementation", "expression of foreign gene", or
                          a short phrase that captures it. Multi-gene papers
                          with mixed types: comma-separate (e.g. "overexpression, knockout").

4. "engineering_type"   — EXACTLY one of:
                            "single-gene engineering"  (one gene engineered in this construct/plant)
                            "multi-gene engineering"   (two or more genes engineered)
                            "NA"                       (genuinely undetermined)
                          The runtime rejects any other string.

5. "gene_construct"     — DNA construct using the GRAMMAR below. If the paper
                          does not state promoter/terminator explicitly, use
                          "NA" in that position rather than guessing.

   Grammar for the construct field:
     * Single transcription unit (TU) / single-gene construct:
           promoter-gene-terminator
       Example: "CaMV35S-AtHB17-NosT"

     * Multi-TU / multi-gene construct: connect TUs with three hyphens "---"
           promoter1-gene1-terminator1---promoter2-gene2-terminator2
       Example: "CaMV35S-GeneA-NosT---UBQ10-GeneB-OcsT"

     * Protein fusion: connect fused protein parts with two colons "::"
           promoter-protein1::protein2-terminator
       Example: "CaMV35S-GFP::AtABF3-NosT"

     * CRISPR gRNA array: connect gRNAs with "+"
           promoter-gRNA1+gRNA2+gRNA3-terminator
       Example: "AtU6-gRNA-FT1+gRNA-FT2-polyT"

     * Use the en-dash "-" as the within-TU separator (ASCII hyphen is fine).

6. "phenotype"          — concise sentence describing the impact on the
                          plant, with numbers/units where the paper gives
                          them. Example:
                          "Overexpression of AtHB17 increases leaf biomass
                           by ~15% in Arabidopsis thaliana."

7. "mechanism"          — the molecular mechanism the paper invokes for the
                          phenotype. Example:
                          "AtHB17 enhances photoprotection by accelerating
                           NPQ relaxation, raising effective quantum yield."
                          Use "NA" if the paper proposes no mechanism.

8. "doi"                — DOI as a bare identifier (no URL prefix).
                          Use the DOI shown in the article header.

9. "pmcid"              — the PMC accession, e.g. "PMC12855588" or
                          "PMC12855588.1". The runtime enforces the pattern.

10. "evidence_quote"    — *** ANTI-HALLUCINATION GUARDRAIL ***
                          A VERBATIM contiguous span (~25-150 words) copied
                          EXACTLY from the ARTICLE BODY shown to you below.
                          Character-for-character, including punctuation,
                          numbers, and units. DO NOT paraphrase. DO NOT add
                          ellipsis. DO NOT summarize. DO NOT translate.
                          DO NOT join non-contiguous sentences.

                          The quote MUST contain at least the gene name AND
                          either (a) the plant species name OR (b) the
                          specific phenotype or mechanism described in this
                          row.

                          If you cannot find a single verbatim span that
                          satisfies this — do NOT emit the row. Return an
                          empty rows list instead. Fabricated quotes are
                          detected by a post-hoc substring check and the
                          row will be discarded.
"""

EXTRACT_USER_TEMPLATE = """\
PMCID: {pmcid}
DOI:   {doi}

Extract every plant-bioengineering DNA construct from the article body
below. One JSON row per construct. If the paper engineers the same gene
into multiple species or with multiple constructs, emit a separate row
for each distinct construct.

REMEMBER: each row's `evidence_quote` MUST appear verbatim in the body
text below. Quotes that paraphrase or summarize will be discarded by
the substring verifier.

--- ARTICLE BODY (main text only; intro/refs/acks already stripped) ---
{body}
--- END ARTICLE BODY ---

Return your JSON object now.
"""

def build_extract_messages(pmcid: str, doi: str | None, body: str) -> list[dict]:
    user = EXTRACT_USER_TEMPLATE.format(
        pmcid=pmcid,
        doi=doi or "NA",
        body=body,
    )
    return [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user",   "content": user},
    ]
