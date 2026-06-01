from .loader import load_rows
from .rules import invoice_total

def totals_by_customer(path):
    out={}
    for row in load_rows(path):
        out.setdefault(row['customer'], 0)
        out[row['customer']] += invoice_total(row)
    return {k: str(v) for k,v in sorted(out.items())}
