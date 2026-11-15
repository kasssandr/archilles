"""Building a Scriptor bundle for a book, and judging whether it may replace the PDF.

A bundle carries citation addresses the PDF path cannot give, but a bad run
costs more than it brings: text that silently went missing, footnotes that were
dropped, page labels that belong to another page. Four conditions decide, all
measured on the run itself (Naht §5, user's release of 2026-09-10):

1. **coverage** -- the text of the PDF's pages is in the master (>= 98 % of
   pages). A page is judged by all of its eight-word windows, not by two
   probes: a probe straddling a footnote boundary fails although the text is
   there, which made the two-probe measure call registers and tables of
   contents lost. A page the windows miss is asked a second time, for its
   words around its own place in any order: a genealogical table has its
   words but not their order.
2. **notes** -- the master defines at least as many footnotes as Scriptor's own
   audit counted with certainty. A gap is a silent loss of apparatus.
3. **attested** -- the bundle only replaces the PDF if it brings citation
   addresses at all (>= 20 % of pages attested).
4. **inherited** -- the share of text standing under another page's number
   stays below 5 %. Good volumes measure 0 to 1.8 %, damage cases 16 % and up
   (51 volumes, September 2026). Scriptor computes it; a bundle whose sidecar
   does not carry the field is not admitted, because nothing else can tell.

The word balance that §2 of the briefing proposed is deliberately not among
them: Scriptor drops running heads and feet on purpose, so every volume loses
4-5 % of its words, the flawless ones included.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_COVERAGE = 0.98
MIN_ATTESTED = 0.20
MAX_INHERITED = 0.05

# A page with less text than this is a plate, a divider or blank -- it carries
# no window worth checking.
_MIN_PAGE_WORDS = 40
_WINDOW_WORDS = 8
# Below this a normalised window is too short to be a distinctive fingerprint.
_MIN_WINDOW_CHARS = 25

# Letters only. Digits are dropped on both sides: a footnote's number is
# page-local in print and document-wide in the master ("...2016.182 Morris"
# against "...2016.[^185] Morris"), so no window straddling an anchor could
# ever match while digits counted -- and nothing else in a window of eight
# words needs them to be distinctive.
_NON_WORD = re.compile(r"[^a-zà-öø-ÿ]+", re.IGNORECASE)
_DEFINITION = re.compile(r"^\[\^[^\]]+\]:", re.MULTILINE)
_AUDIT_CERTAIN = re.compile(r"(\d+) certain footnotes")
# Everything the spec writes into the text that is not the text: page markers
# and their anchors, region marks, footnote anchors and definition heads.
_SPEC_MARKUP = re.compile(r"\[p\.[^\]]*\]|\{#p-[^}]*\}|\[region:[^\]]*\]|\[\^[^\]]+\]:?")

# The second test, for a page the windows call lost. A genealogical table is
# printed in two dimensions and its text layer runs in whatever order the
# setter placed the boxes: Wolf, *Verwandtschaft – Erbrecht – Königswahlen*,
# lost 66 pages to the windows, nearly all of them tables, while every word of
# every one of them stood in the master (97 to 100 %, the gaps being the halves
# of hyphenated words). Order is what the windows test; the words are what
# the page is. They are looked for only around the page's own place -- from
# the page before to the page after -- because in a book of a thousand pages
# nearly every word of any page stands *somewhere*, and a page that went
# missing would pass a search over the whole master.
_MIN_LOCAL_SHARE = 0.95
# Shorter words are found inside nearly any stretch of text and prove nothing.
_MIN_LOCAL_WORD_CHARS = 4


def _normalise(text: str) -> str:
    """Letters and digits only, lowercased.

    Hyphenation, line breaks, spacing and punctuation differ between a PDF's
    text layer and the reflowed master by design; none of them may cause a
    miss.
    """
    return _NON_WORD.sub("", text.lower())


def _haystack(master_text: str) -> str:
    """The master as pure text: metadata block and spec markup removed."""
    from scriptor.reflow.regions import strip_metadata_block

    return _normalise(_SPEC_MARKUP.sub(" ", strip_metadata_block(master_text)))


def front_matter_pages(master: Path) -> set[int]:
    """Physical pages the master declares to be front matter.

    Two ways a page gets in. Its own page marker may stand in a front-matter
    region. Or it may have no marker at all while the stretch it falls in --
    between the markers of the pages around it -- opens one: the table of
    contents is rebuilt as a link list and the list of figures is reordered,
    both on purpose (spec §4.4), so those pages leave no marker behind and
    their printed text is not in the master and never was meant to be. They
    also leave the default search, so the coverage question does not apply to
    them.

    A page lost by accident leaves no marker either, but the stretch it falls
    in opens no front-matter region -- which is what keeps this from excusing
    a real loss. An unreadable bundle excludes nothing.
    """
    from scriptor.document import load_bundle, parse_prepared, region_at

    from src.archilles.constants import SectionType
    from src.extractors.scriptor_extractor import region_to_section_type

    def is_front(region: str) -> bool:
        return region_to_section_type(region) == SectionType.FRONT_MATTER

    try:
        bundle = load_bundle(master)
    except Exception as exc:
        # Loud, not silent: without the bundle every page is judged, and a
        # volume whose contents were rebuilt then reads as losing them.
        logger.warning("%s: bundle not readable (%s) -- no page exempted", master, exc)
        return set()
    if bundle is None:
        logger.warning("%s: no metadata block -- no page exempted", master)
        return set()

    doc = parse_prepared(bundle.text)
    marks = [
        (offset, entry.pos)
        for (_label, offset), entry in zip(doc.page_marks, bundle.resolve_marks(doc))
        if entry is not None
    ]

    out: set[int] = set()
    previous_offset, previous_pos = 0, 0
    for offset, pos in marks:
        if is_front(region_at(doc, offset)):
            out.add(pos)
        if pos > previous_pos + 1:
            opens_front = is_front(region_at(doc, previous_offset)) or any(
                is_front(name) for name, mark in doc.region_marks
                if previous_offset <= mark <= offset
            )
            if opens_front:
                out.update(range(previous_pos + 1, pos))
        previous_offset, previous_pos = offset, pos
    return out


def page_neighbourhoods(master: Path) -> Callable[[int], str | None] | None:
    """For a physical page, the master's text from the page before to the page after.

    Normalised as the haystack is, with the definitions of the notes anchored
    in that stretch added -- the master gathers them at its end (spec §4.3),
    and a page's apparatus is part of the page. ``None`` where the master
    cannot be read as a bundle: then there is no place to look, and no page
    gets a second test.
    """
    from scriptor.document import load_bundle, parse_prepared

    try:
        bundle = load_bundle(master)
    except Exception as exc:
        logger.warning("%s: bundle not readable (%s) -- no second coverage test", master, exc)
        return None
    if bundle is None:
        return None
    doc = parse_prepared(bundle.text)
    marks = [
        (offset, entry.pos)
        for (_label, offset), entry in zip(doc.page_marks, bundle.resolve_marks(doc))
        if entry is not None
    ]
    if not marks:
        return None
    anchored = [(f.anchor_offset, f.definition) for f in doc.footnotes
                if f.anchor_offset is not None]

    def around(pos: int) -> str | None:
        start = next((o for o, p in reversed(marks) if p < pos), 0)
        end = next((o for o, p in marks if o > start and p > pos + 1), len(doc.body))
        if not any(start <= o < end for o, p in marks if p == pos):
            # The page has no marker of its own here: nothing says where it is.
            return None
        notes = " ".join(d for o, d in anchored if start <= o < end)
        return _normalise(_SPEC_MARKUP.sub(" ", doc.body[start:end] + " " + notes))

    return around


def _words_in(words: list[str], local: str) -> bool:
    """Whether the page's words stand in ``local``, order aside."""
    norm = [w for w in (_normalise(t) for t in words) if len(w) >= _MIN_LOCAL_WORD_CHARS]
    if not norm:
        return False
    return sum(w in local for w in norm) >= _MIN_LOCAL_SHARE * len(norm)


def _windows(words: list[str]) -> list[str]:
    """Every eight-word window of a page, back to back."""
    out = [
        _normalise(" ".join(words[i:i + _WINDOW_WORDS]))
        for i in range(0, max(len(words) - _WINDOW_WORDS, 0), _WINDOW_WORDS)
    ]
    return [w for w in out if len(w) >= _MIN_WINDOW_CHARS]


def text_coverage(
    pdf_path: Path,
    master_text: str,
    skip_pages: set[int] | None = None,
    neighbourhood: Callable[[int], str | None] | None = None,
) -> tuple[float | None, list[int]]:
    """Share of the PDF's pages whose text is in the master, and the lost ones.

    The page is the unit, the windows are how a page is judged: it counts as
    present when at least half of its eight-word windows are in the master
    (the criterion of ``baltrusch_windows.py``). Counting windows instead of
    pages would measure something else -- every page loses the window that
    holds its running head and the one that holds its foot, both of which
    Scriptor removes on purpose, and a volume in perfect shape then reads
    92 to 96 %.

    ``skip_pages`` names physical pages the question does not apply to (see
    :func:`front_matter_pages`). Where that leaves no page to check -- a short
    extract that is front matter all through -- the share is ``None``: unknown,
    which is not the same as nothing found.

    ``neighbourhood`` (see :func:`page_neighbourhoods`) gives a page the
    windows call lost a second test: present if 95 % of its words stand in the
    master around its own place, in any order. Without it, the windows decide
    alone.
    """
    import pymupdf

    skip = skip_pages or set()
    haystack = _haystack(master_text)
    checked = present = 0
    lost: list[int] = []
    with pymupdf.open(pdf_path) as doc:
        for number, page in enumerate(doc, 1):
            if number in skip:
                continue
            words = page.get_text().split()
            if len(words) < _MIN_PAGE_WORDS:
                continue
            windows = _windows(words)
            if not windows:
                continue
            checked += 1
            if sum(w in haystack for w in windows) >= len(windows) / 2:
                present += 1
            elif neighbourhood and (local := neighbourhood(number)) and _words_in(words, local):
                present += 1
            else:
                lost.append(number)
    if not checked:
        return None, lost
    return present / checked, lost


def audit_certain_notes(audit_text: str) -> int | None:
    """The footnotes Scriptor's audit counted with certainty, or None."""
    match = _AUDIT_CERTAIN.search(audit_text)
    return int(match.group(1)) if match else None


def definition_count(master_text: str) -> int:
    """``[^N]:`` definitions in the master."""
    return len(_DEFINITION.findall(master_text))


@dataclass
class BundleCheck:
    """What the four conditions measured, and whether the bundle is admitted."""

    coverage: float | None = None
    lost_pages: list[int] = field(default_factory=list)
    definitions: int | None = None
    certain_notes: int | None = None
    attested: float | None = None
    inherited: float | None = None
    reasons: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def admitted(self) -> bool:
        return not self.reasons and self.error is None

    def as_dict(self) -> dict:
        return {
            "coverage": None if self.coverage is None else round(self.coverage, 4),
            "lost_pages": self.lost_pages[:20],
            "definitions": self.definitions,
            "certain_notes": self.certain_notes,
            "attested": self.attested,
            "inherited": self.inherited,
            "admitted": self.admitted,
            "reasons": self.reasons,
            "error": self.error,
        }


def check_bundle(master: Path, pdf_path: Path) -> BundleCheck:
    """Measure the four conditions on a finished Scriptor run.

    Reads the master and its sidecars; opens the PDF once. Never raises: a
    condition that cannot be measured is a reason to refuse, not a crash in
    the middle of a batch.
    """
    check = BundleCheck()
    try:
        master_text = master.read_text(encoding="utf-8")
    except OSError as exc:
        check.error = f"master unreadable: {exc}"
        return check

    # 1 -- text coverage
    try:
        check.coverage, check.lost_pages = text_coverage(
            pdf_path, master_text, front_matter_pages(master),
            page_neighbourhoods(master))
    except Exception as exc:
        check.error = f"coverage not measurable: {type(exc).__name__}: {exc}"
        return check
    if check.coverage is None:
        check.reasons.append("no page could be checked for text coverage")
    elif check.coverage < MIN_COVERAGE:
        check.reasons.append(
            f"text coverage {check.coverage:.1%} < {MIN_COVERAGE:.0%}"
            + (f" ({len(check.lost_pages)} pages lost)" if check.lost_pages else "")
        )

    # 2 -- notes against the audit
    check.definitions = definition_count(master_text)
    audit = master.with_name(master.name + ".audit.txt")
    if audit.exists():
        check.certain_notes = audit_certain_notes(audit.read_text(encoding="utf-8"))
    if check.certain_notes is not None and check.definitions < check.certain_notes:
        check.reasons.append(
            f"{check.definitions} definitions < {check.certain_notes} certain footnotes"
        )

    # 3 and 4 -- what the pagination sidecar witnessed
    sidecar = master.with_name(master.name + ".pagination.json")
    profile: dict = {}
    if sidecar.exists():
        try:
            profile = json.loads(sidecar.read_text(encoding="utf-8")).get("profile", {})
        except (OSError, json.JSONDecodeError) as exc:
            check.reasons.append(f"pagination sidecar unreadable: {exc}")
    else:
        check.reasons.append("no pagination sidecar")

    check.attested = profile.get("attested")
    check.inherited = profile.get("inherited")

    if check.attested is None:
        if sidecar.exists():
            check.reasons.append("sidecar names no attested share")
    elif check.attested < MIN_ATTESTED:
        check.reasons.append(
            f"only {check.attested:.0%} of pages attested < {MIN_ATTESTED:.0%}"
        )

    # A missing field counts as unknown, and unknown is not admitted: nothing
    # but the producer can count it (Scriptor a77f765).
    if check.inherited is None:
        if sidecar.exists():
            check.reasons.append("sidecar names no inherited share (Scriptor too old)")
    elif check.inherited >= MAX_INHERITED:
        check.reasons.append(
            f"{check.inherited:.0%} of the text cites as another page >= {MAX_INHERITED:.0%}"
        )

    return check


def open_decisions(master: Path) -> int:
    """Lines in the decisions sidecar -- the handwork the volume still invites."""
    path = master.with_name(master.name + ".decisions.txt")
    if not path.exists():
        return 0
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
