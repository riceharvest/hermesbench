from decimal import Decimal

def parse_money(s):
    return Decimal(str(s).replace('$','').replace(',',''))

def load_rows(path):
    rows=[]
    for line in open(path):
        if line.startswith('invoice_id'): continue
        invoice_id, customer, subtotal, tax_rate, discount_code = line.strip().split(',')
        rows.append(dict(invoice_id=invoice_id, customer=customer, subtotal=parse_money(subtotal), tax_rate=Decimal(tax_rate), discount_code=discount_code))
    return rows
