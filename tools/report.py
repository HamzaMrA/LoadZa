"""Write the printable loading plan and the spreadsheet for a plan file.

    python -m tools.report data/demo/job.json data/plans/plan.json
    python -m tools.report <job> <plan> --outdir reports --pdf-only

Needs the viz extra:  pip install -e ".[viz]"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.report import item_list_xlsx, loading_plan_pdf
from core.io import load_job, load_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a LoadZa loading plan")
    parser.add_argument("job", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--outdir", type=Path, default=Path("data/reports"))
    parser.add_argument("--pdf-only", action="store_true")
    parser.add_argument("--xlsx-only", action="store_true")
    args = parser.parse_args()

    job = load_job(args.job)
    plan = load_plan(args.plan)

    if not args.xlsx_only:
        path = loading_plan_pdf(job, plan, args.outdir / f"{plan.plan_id}.pdf")
        print(f"pdf   {path}")
    if not args.pdf_only:
        path = item_list_xlsx(job, plan, args.outdir / f"{plan.plan_id}.xlsx")
        print(f"xlsx  {path}")


if __name__ == "__main__":
    main()
