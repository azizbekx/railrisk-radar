"""Eval cases for the data chat assistant (views/chat.py). Expected values are computed from core.dataset,
so the checks stay correct if the data or the TRI explanation changes."""
import re
from dataclasses import dataclass, field

from core import dataset as ds

ID_RE = re.compile(r"SUPP_\d+")
TRI, FHS, CRS = "Total_Risk_Index", "Financial_Health_Score", "Credit_Rating_Score"
DEL, COMP, CYBER = "Supplier Delivery Rating", "Compliance_Risk_Score", "Digital_Security_Score"
LEVEL_COLS = [f"{c}_Level" for c in ds.SCORES]


@dataclass
class Case:
    name: str
    question: str
    checks: callable                      # (Run) -> list[(check, ok, detail)]
    shortlist: list = field(default_factory=list)

    def prompt(self) -> str:
        # exactly what views/chat.py sends
        return self.question + f"\n\n(Buyer's current shortlist: {', '.join(self.shortlist) or 'empty'})"


@dataclass
class Run:
    answer: str
    steps: list

    @property
    def calls(self) -> list[tuple[str, dict, object]]:
        """(tool name, args, result) for every tool call."""
        out, pending = [], []
        for s in self.steps:
            if s["type"] == "tool_call":
                pending.append(s)
            elif s["type"] == "tool_result" and pending:
                c = pending.pop(0)
                out.append((c["name"], c.get("args") or {}, s["content"]))
        return out

    def used(self, *names) -> bool:
        return any(n in names for n, _, _ in self.calls)

    def results(self, *names) -> list:
        return [r for n, _, r in self.calls if n in names and isinstance(r, dict)]

    @property
    def ids(self) -> list[str]:
        return list(dict.fromkeys(ID_RE.findall(self.answer)))

    @property
    def bold_ids(self) -> list[str]:
        return [i for b in re.findall(r"\*\*(.+?)\*\*", self.answer) for i in ID_RE.findall(b)]


def chk(name, ok, detail=""):
    return (name, bool(ok), detail)


def row(sid):
    return ds.df().loc[sid]


def has_number(text: str, value: float, tol: float = 0.51) -> bool:
    return any(abs(float(x) - value) <= tol for x in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", text.replace(",", "")))


def lead_id(r: Run) -> str | None:
    return (r.bold_ids or r.ids or [None])[0]


def covered(r: Run, tools: tuple, ids: list[str]) -> set:
    """Supplier IDs that the given tools actually returned data for."""
    got = set()
    for res in r.results(*tools):
        sup = res.get("suppliers")
        if isinstance(sup, list):
            got |= {s if isinstance(s, str) else s.get("supplierID") for s in sup}
    return got & set(ids)


# ---------- generic checks (every case) ----------

LABELS = [(re.compile(r"\b(?:TRI|Total[_ ]Risk[_ ]Index)\b", re.I), TRI),
          (re.compile(r"delivery", re.I), DEL),
          (re.compile(r"confirmation", re.I), "Order Confirmation Rate"),
          (re.compile(r"cyber", re.I), CYBER)] + \
         [(re.compile(re.escape(ds.label(c)).replace(r"\ ", "[_ ]"), re.I), c) for c in ds.SCORES]
PCT_OK = {DEL, "Order Confirmation Rate"}


def _first_number(text: str, col: str):
    m = re.search(r"(?<![\w.+\-])(\d+(?:\.\d+)?)(\s*%|\s*(?:pts|points|percent))?", text)
    if not m or (m.group(2) and col not in PCT_OK):
        return None
    return float(m.group(1))


def number_mismatches(answer: str) -> list[str]:
    """Numbers stated next to a supplier ID and a column label that disagree with the dataset."""
    bad, header = [], None
    for line in answer.splitlines():
        ids = [i for i in dict.fromkeys(ID_RE.findall(line)) if i in ds.df().index]
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not ids and not all(set(c) <= set("-: ") for c in cells):
                header = cells
            if len(ids) == 1 and header and len(header) == len(cells):
                for h, cell in zip(header, cells):
                    col = next((c for rx, c in LABELS if rx.search(h)), None)
                    if col and not ID_RE.search(cell) and not re.search(r"avg|average|weight|pct|percentile|rank", h, re.I):
                        v = _first_number(cell.replace(",", ""), col)
                        if v is not None and abs(v - float(row(ids[0])[col])) > 0.51:
                            bad.append(f"{ids[0]} {col}: said {v}, data {row(ids[0])[col]}")
            continue
        header = None
        if len(ids) != 1:
            continue
        for rx, col in LABELS:
            for m in rx.finditer(line):
                if re.search(r"(average|avg|mean|median|threshold|target)\W{0,3}$", line[max(0, m.start() - 12):m.start()], re.I):
                    continue  # "dataset average TRI: 50.2" is not this supplier's value
                tail = line[m.end():m.end() + 30]
                tail = re.split(r"[;,]|\bvs\b|\baverage\b|\bweight", tail)[0]
                sep = re.match(r"[^\d\n|]{0,18}", tail).group(0)
                filler = re.sub(r"\b(score|rating|risk|index|level|of|is|at|was|stands|sits|=)\b", "", sep, flags=re.I)
                if re.search(r"[A-Za-z]{3,}|[<>≥≤]", filler):  # another word or a criterion ("> 97 %")
                    continue  # another word in between, probably not this label's value
                v = _first_number(tail[len(sep):], col)
                if v is not None and abs(v - float(row(ids[0])[col])) > 0.51:
                    bad.append(f"{ids[0]} {col}: said {v}, data {row(ids[0])[col]}")
    return list(dict.fromkeys(bad))


def generic(r: Run, rec: dict, max_steps: int) -> list:
    errors = [s["content"] for s in r.steps if s["type"] == "error"]
    unknown = [i for i in r.ids if i not in ds.df().index]
    leaks = [t for t in ("<think>", "</think>", "<tool_call>", "</tool_call>", '"name":', "<|") if t in r.answer]
    mism = number_mismatches(r.answer)
    return [chk("no_error", not errors, "; ".join(map(str, errors))[:200]),
            chk("answered", r.answer.strip() and r.answer.strip() != "(no answer)" and len(r.answer) > 20,
                r.answer[:80]),
            chk("ids_exist", not unknown, ", ".join(unknown)),
            chk("numbers_match", not mism, "; ".join(mism)[:300]),
            chk("no_leak", not leaks, ", ".join(leaks)),
            chk("within_steps", rec["llm_calls"] <= max_steps, f"{rec['llm_calls']} LLM calls")]


# ---------- the cases ----------

def q1_checks(r: Run):
    ids = ["SUPP_00012", "SUPP_00450", "SUPP_00731"]
    best = ds.df().loc[ids, FHS].idxmin()
    credit = int(row(best)[CRS])
    return [chk("names_lowest_fin_risk", lead_id(r) == best, f"lead={lead_id(r)} expected={best}"),
            chk("states_fin_health", has_number(r.answer, row(best)[FHS], 0)),
            chk("mentions_credit", re.search(r"credit", r.answer, re.I) and has_number(r.answer, credit, 0),
                f"Credit_Rating_Score {credit} {row(best)[CRS + '_Level']}"),
            chk("tool_compare_or_get", covered(r, ("compare_suppliers", "get_suppliers"), ids) == set(ids),
                str([n for n, _, _ in r.calls]))]


def q2_checks(r: Run):
    e = ds.explain("SUPP_00018")
    top3 = [p["label"] for p in e["drivers_up"][:3]]
    said = [lab for lab in top3 if re.search(re.escape(lab.replace(" Risk", "")), r.answer, re.I)]
    return [chk("called_explain_risk", any(res.get("id") == "SUPP_00018" for res in r.results("explain_risk")),
                str([n for n, _, _ in r.calls])),
            chk("states_tri", has_number(r.answer, e["total_risk_index"], 0), f"TRI {e['total_risk_index']}"),
            chk("top_drivers", len(said) >= 2, f"top3={top3} mentioned={said}")]


def no_critical(sid) -> bool:
    x = row(sid)
    return not (x[LEVEL_COLS] == "Critical").any() and x["Total_Risk_Index_Level"] != "Critical"


def p3_checks(r: Run):
    added = list(dict.fromkeys(i for res in r.results("add_to_shortlist") for i in res.get("added", [])))
    bad = [i for i in added if not (row(i)["Sourcing Risk Level"] == "Low" and row(i)[DEL] > 97 and no_critical(i))]
    return [chk("called_shortlist", added, str([n for n, _, _ in r.calls])),
            chk("five_added", len(added) == 5, f"{len(added)} added"),
            chk("all_meet_criteria", added and not bad, "violating: " + ", ".join(
                f"{i}(src={row(i)['Sourcing Risk Level']},del={row(i)[DEL]},crit={not no_critical(i)})" for i in bad))]


SHORTLIST = ["SUPP_00012", "SUPP_00450", "SUPP_00731", "SUPP_00018", "SUPP_00042"]


def p4_checks(r: Run):
    cmp = ds.compare(SHORTLIST, [COMP, CYBER])["columns"]
    want = {}
    for col in (COMP, CYBER):
        vals = cmp[col]["values"]
        want[col] = ([k for k, v in vals.items() if v == min(vals.values())],
                     [k for k, v in vals.items() if v == max(vals.values())])
    miss = [f"{ds.label(c)} {kind}" for c, (lo, hi) in want.items()
            for kind, grp in (("lowest", lo), ("highest", hi)) if not set(grp) & set(r.ids)]
    return [chk("tool_covers_shortlist", covered(r, ("compare_suppliers", "get_suppliers"), SHORTLIST) == set(SHORTLIST),
                str([(n, a) for n, a, _ in r.calls])[:200]),
            chk("mentions_shortlist", len(set(r.ids) & set(SHORTLIST)) >= 4, f"{len(set(r.ids) & set(SHORTLIST))}/5"),
            chk("names_best_and_worst", not miss, ", ".join(miss))]


def high_src_checks(r: Run):
    d = ds.df()
    hs = d[d["Sourcing Risk Level"] == "High"].sort_values(TRI)
    cutoff = hs[TRI].iloc[4]
    elig = set(hs[hs[TRI] <= cutoff].index)
    must = set(hs[hs[TRI] < cutoff].index)
    got = set(r.ids)
    return [chk("used_find", r.used("find_suppliers")),
            chk("top5_correct", must <= got and len(got & elig) >= 5,
                f"missing={sorted(must - got)} got_eligible={len(got & elig)}"),
            chk("no_wrong_ids", got <= elig, ", ".join(sorted(got - elig)))]


def complexity_checks(r: Run):
    means = ds.df().groupby("Supply Chain Complexity")[DEL].mean()
    miss = [f"{g} {v:.2f}" for g, v in means.items() if not has_number(r.answer, v, 0.06)]
    return [chk("used_stats", r.used("column_stats", "find_suppliers")),
            chk("group_means", not miss, "missing " + ", ".join(miss))]


COUNTRIES = ["Germany", "China", "India", "France", "Italy", "Spain", "Poland", "United States", "USA", "Japan",
             "Mexico", "Brazil", "Turkey", "Czech", "Austria", "Switzerland", "United Kingdom", "Netherlands",
             "Sweden", "Korea", "Vietnam", "Romania", "Hungary", "Canada", "Taiwan"]


def country_checks(r: Run):
    a = r.answer
    says_no = re.search(r"(\bno\b|\bnot\b|n't|without|lacks?|unavailable|anonymi[sz]ed)[^.\n]{0,80}(countr|location|geograph)"
                        r"|(countr|location)[^.\n]{0,80}(\bnot\b|n't|unavailable|no\b)", a, re.I)
    named = [c for c in COUNTRIES if re.search(rf"\b{c}\b", a)]
    return [chk("says_not_in_data", says_no), chk("no_hallucinated_country", not named, ", ".join(named))]


NAME_ID = "SUPP_00777"


def name_checks(r: Run):
    tri = int(row(NAME_ID)[TRI])
    return [chk("resolved_id", NAME_ID in r.ids, f"expected {NAME_ID}"),
            chk("states_tri", has_number(r.answer, tri, 0), f"TRI {tri}")]


def typo_checks(r: Run):
    x = row("SUPP_00018")
    return [chk("resolved_id", "SUPP_00018" in r.ids),
            chk("states_tri", has_number(r.answer, x[TRI], 0), f"TRI {x[TRI]}"),
            chk("states_delivery", has_number(r.answer, x[DEL], 0.051), f"delivery {x[DEL]}")]


TWENTY = [f"SUPP_{i:05d}" for i in range(137, 10000, 491)][:20]


def twenty_checks(r: Run):
    t = ds.df().loc[TWENTY, TRI]
    hi, lo = set(t[t == t.max()].index), set(t[t == t.min()].index)
    return [chk("tool_covers_20", covered(r, ("compare_suppliers", "get_suppliers"), TWENTY) == set(TWENTY),
                f"{len(covered(r, ('compare_suppliers', 'get_suppliers'), TWENTY))}/20"),
            chk("names_riskiest", hi & set(r.ids), f"expected one of {sorted(hi)} (TRI {t.max()})"),
            chk("names_safest", lo & set(r.ids), f"expected one of {sorted(lo)} (TRI {t.min()})")]


CASES = [
    Case("jury_q1_financial", "Which of SUPP_00012, SUPP_00450 and SUPP_00731 has the lowest financial risk?", q1_checks),
    Case("jury_q2_tri_why", "Why is the Total Risk Index of SUPP_00018 so high?", q2_checks),
    Case("preset_shortlist5", "Find 5 easy-to-replace suppliers with delivery rating above 97% and no Critical scores, "
         "and shortlist them", p3_checks),
    Case("preset_compare_shortlist", "How does my shortlist compare on compliance and cyber risk?", p4_checks,
         shortlist=SHORTLIST),
    Case("high_sourcing_top5", "Which 5 suppliers with High sourcing risk have the lowest Total Risk Index?",
         high_src_checks),
    Case("delivery_by_complexity", "What is the average supplier delivery rating for each supply chain complexity level?",
         complexity_checks),
    Case("country_not_in_data", "Which country is SUPP_00042 in?", country_checks),
    Case("name_lookup", f"How risky is {ds.df().loc[NAME_ID, 'Supplier Name']}? Give me its ID and Total Risk Index.",
         name_checks),
    Case("typo_id", "whats the TRI and delivery rating of supp 18", typo_checks),
    Case("compare_20", "Compare these suppliers on Total Risk Index and tell me the riskiest and the safest one: "
         + ", ".join(TWENTY), twenty_checks),
]
