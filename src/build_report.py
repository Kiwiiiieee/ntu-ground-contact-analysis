"""
Build the two-page report from the data in one step:
  1. src/report_numbers.py  -> report/numbers.tex and docs/decision_log.md
     (stops if the baseline or any claim in the report no longer holds)
  2. pdflatex twice in report/ -> report/report.pdf
  3. page check: body at most 3 pages, appendix (notes + figures) at most 2

Example
    uv run src/build_report.py
"""

import re
import subprocess
import sys

from run_gmat import ROOT

REPORT = ROOT / "report"
MAX_BODY_PAGES = 3
MAX_APPENDIX_PAGES = 2


def main() -> int:
    step = subprocess.run([sys.executable, str(ROOT / "src" / "report_numbers.py")])
    if step.returncode != 0:
        return step.returncode
    for _ in range(2):                          # second pass resolves references
        run = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "report.tex"],
                             cwd=REPORT, capture_output=True, text=True)
        if run.returncode != 0:
            print(run.stdout[-3000:])
            return run.returncode
    pages = re.search(r"Output written on report\.pdf \((\d+) pages?", run.stdout)
    n = int(pages.group(1)) if pages else -1
    # The body ends at \label{body-end}; it may use at most 3 pages, and the
    # appendix (methodological notes + supplementary figures) at most 2 more.
    aux = (REPORT / "report.aux").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\\newlabel\{body-end\}\{\{[^}]*\}\{(\d+)\}", aux)
    body = int(m.group(1)) if m else -1
    print(f"report/report.pdf: {n} page(s); body ends on page {body}; appendix {n - body} page(s)")
    if not 1 <= body <= MAX_BODY_PAGES or n - body > MAX_APPENDIX_PAGES:
        print(f"ERROR: the body must be at most {MAX_BODY_PAGES} pages and the appendix at most {MAX_APPENDIX_PAGES}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
