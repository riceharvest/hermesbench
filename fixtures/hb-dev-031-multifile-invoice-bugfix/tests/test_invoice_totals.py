from billing.report import totals_by_customer

def test_totals_by_customer_policy_order():
    assert totals_by_customer('data/invoices.csv') == {'Ada':'223.50','Ben':'256.50','Cy':'94.50'}
