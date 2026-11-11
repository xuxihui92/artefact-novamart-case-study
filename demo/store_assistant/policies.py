"""Policy document loading, keyword search, and clause selection."""
import re
from pathlib import Path

from .config import CLAUSE_HEADER, REQUIRED_CLAUSES, ROOT, WINDOW
from .text import terms


class PolicyLibrary:
    def __init__(self, policies_dir=None):
        policies_dir = Path(policies_dir or ROOT / "policies")
        self.policies = {}
        self.clauses = {}
        for path in sorted(policies_dir.glob("RET-*.md")):
            header, *sections = path.read_text(encoding="utf-8").strip().split("\n## ")
            title, version = header.strip().splitlines()
            version = version.removeprefix("Version: ")
            doc = {
                "id": path.stem,
                "title": title.removeprefix("# "),
                "version": version,
                "sections": [],
            }
            for section in sections:
                heading, body = section.split("\n", 1)
                match = CLAUSE_HEADER.fullmatch(heading)
                if not match or not match[1].startswith(path.stem + ".") or not body.strip():
                    raise ValueError(f"{path.name}: invalid or missing clause ID in {heading!r}")
                clause_id, clause_title = match.groups()
                if clause_id in self.clauses:
                    raise ValueError(f"Duplicate policy clause ID: {clause_id}")
                clause = {
                    "id": clause_id,
                    "document": path.stem,
                    "title": clause_title,
                    "text": body.strip(),
                    "version": version,
                }
                doc["sections"].append(clause)
                self.clauses[clause["id"]] = clause
            self.policies[path.stem] = doc
        missing = REQUIRED_CLAUSES - self.clauses.keys()
        if missing:
            raise ValueError("Missing required policy clauses: " + ", ".join(sorted(missing)))
        self.return_windows = {}
        for category, clause_id in (("general", "RET-01.1"), ("electronics", "RET-02.1")):
            match = WINDOW.search(self.clauses[clause_id]["text"])
            if not match:
                raise ValueError(f"{clause_id}: expected a return window in calendar days from purchase")
            self.return_windows[category] = (clause_id, int(match[1]))

    def search(self, query):
        query_terms = terms(query)
        ranked = []
        for clause in self.clauses.values():
            title_terms = terms(clause["title"])
            content_terms = terms(clause["text"])
            score = 3 * len(query_terms & title_terms) + len(query_terms & content_terms)
            if score or not query.strip():
                ranked.append((score, clause))
        return [clause for _, clause in sorted(ranked, key=lambda pair: -pair[0])][:6]

    def applicable_policy(self, message, words, facts):
        if "refund" in words:
            return ("RET-03.1",)
        if "exchange" in words:
            return ("RET-03.2",)
        if re.search(r"\bfinal[- ]sale\b", message, re.I):
            return ("RET-02.3",)
        if "marketplace" in words:
            return ("RET-01.3",)
        if "electronics" in words:
            if facts.get("opened") is True or facts.get("defect") is True:
                return ("RET-02.2",)
            return ("RET-02.1",)
        if re.search(r"\bdamaged on arrival\b|\bincomplete (?:order|shipment|delivery)\b", message, re.I) or (
            "damaged" in words and words & {"arrival", "arrived", "delivery", "package"}
        ):
            return ("RET-05.2",)
        if facts.get("defect") is True:
            return ("RET-03.3",)
        if "receipt" in words or re.search(r"\bproof of purchase\b", message, re.I):
            if facts.get("used") is True or facts.get("resalable") is False:
                return ("RET-01.1", "RET-01.2")
            return ("RET-01.2",)
        if "online" in words and "return" in words:
            return ("RET-01.3",)
        if re.search(r"\bprice[- ]?match\b", message, re.I) or (
            "price" in words and words & {"match", "matching", "lower", "competitor"}
        ):
            return ("RET-04.1",)
        if words & {"coupon", "promotion", "promo"}:
            return ("RET-04.2",)
        if "member" in words or "discount" in words:
            return ("RET-04.3",)
        if "pickup" in words or re.search(r"\bready[- ]for[- ]pickup\b", message, re.I):
            return ("RET-05.1",)
        if words & {"delivery", "delivered"} or re.search(r"\bmissed delivery\b|\bnot received\b", message, re.I):
            return ("RET-05.3",)
        if re.fullmatch(
            r"(?:what is (?:the |your )?)?(?:standard )?return(?:s)? (?:window|policy)[?!. ]*"
            r"|how do i return (?:an item|something)[?!. ]*",
            message,
            re.I,
        ):
            return ("RET-01.1",)
        return ()
