from decimal import Decimal
DISCOUNTS={'NONE':Decimal('0.00'),'SAVE10':Decimal('0.10'),'VIP15':Decimal('0.15'),'FREESHIP':Decimal('0.00')}

def invoice_total(row):
    # BUG: tax is applied before discount; policy requires discount then tax.
    discounted = row['subtotal'] - (row['subtotal'] * DISCOUNTS[row['discount_code']])
    return (row['subtotal'] * (Decimal('1.0') + row['tax_rate']) - (row['subtotal'] * DISCOUNTS[row['discount_code']])).quantize(Decimal('0.01'))
