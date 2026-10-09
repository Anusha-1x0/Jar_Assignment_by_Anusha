"""Rebuild all assignment tables from the three original PDFs. Run in .venv."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import importlib.metadata as metadata
import json
import re
import sys
import numpy as np
import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
TABLES = ROOT / 'analysis'
FILES = {
    'orders': 'List_of_Orders_-_List_of_Orders.pdf',
    'details': 'Order_Details_-_Order_Details.pdf',
    'targets': 'Sales_target_-_Sales_target.pdf',
}
COLUMNS = {
    'orders': ['order_id', 'order_date', 'customer_name', 'state', 'city'],
    'details': ['order_id', 'amount', 'profit', 'quantity', 'category', 'subcategory'],
    'targets': ['month', 'category', 'target'],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def extract(kind):
    """Use original PDF text objects, not geometric table cell clipping.

    In these exports every data cell is a text object. This preserves long
    states which extend across a drawn column border. Validate every row.
    """
    source = ROOT / FILES[kind]
    rows = []
    pattern = r'B-\d{5}' if kind != 'targets' else r'[A-Z][a-z]{2}-\d{2}'
    for page_no, page in enumerate(PdfReader(source).pages, 1):
        pieces = []
        page.extract_text(visitor_text=lambda text, *_: pieces.append(text.strip())
                          if text.strip() else None)
        current = []
        page_row = 0

        def commit(cells):
            nonlocal page_row
            require(len(cells) == len(COLUMNS[kind]),
                    f'{source.name} page {page_no}: invalid cells {cells}')
            page_row += 1
            rows.append(cells + [source.name, page_no, page_row])

        for text in pieces:
            if re.fullmatch(pattern, text):
                if current:
                    commit(current)
                current = [text]
            elif current:
                current.append(text)
        if current:
            commit(current)
    return pd.DataFrame(rows, columns=COLUMNS[kind] +
                        ['source_file', 'source_page', 'source_row'])


def ratio(numerator, denominator):
    return numerator / denominator.replace(0, np.nan)


def aggregate(frame, keys):
    out = frame.groupby(keys, observed=True).agg(
        sales=('amount', 'sum'), profit=('profit', 'sum'),
        orders=('order_id', 'nunique'), lines=('order_id', 'size'),
        units=('quantity', 'sum')).reset_index()
    out['profit_per_order'] = ratio(out.profit, out.orders)
    out['margin_pct'] = 100 * ratio(out.profit, out.sales)
    out['sales_per_order'] = ratio(out.sales, out.orders)
    out['profit_per_line'] = ratio(out.profit, out.lines)
    return out


def main():
    require(sys.prefix != sys.base_prefix, 'Activate the project virtual environment.')
    for folder in [DATA, TABLES]:
        folder.mkdir(exist_ok=True)
    orders, details, targets = [extract(k) for k in FILES]
    require([len(orders), len(details), len(targets)] == [500, 1500, 36],
            'Source row counts differ from the inspected PDFs.')
    for kind, frame in zip(FILES, [orders, details, targets]):
        require(not frame[COLUMNS[kind]].isna().any().any(), f'Missing {kind} values')
        require(not frame[COLUMNS[kind]].eq('').any().any(), f'Empty {kind} values')
    orders.order_date = pd.to_datetime(orders.order_date, format='%d-%m-%Y')
    targets.month = pd.to_datetime(targets.month, format='%b-%y')
    for field in ['amount', 'profit', 'quantity']:
        details[field] = pd.to_numeric(details[field], errors='raise').astype('int64')
    targets.target = pd.to_numeric(targets.target, errors='raise').astype('int64')
    require(orders.order_id.is_unique, 'Duplicate order keys')
    require(not targets.duplicated(['month', 'category']).any(), 'Duplicate target keys')
    require((details.amount >= 0).all() and (details.quantity > 0).all(), 'Invalid amounts/units')
    require((targets.target > 0).all(), 'Nonpositive target')
    require(set(details.category) == set(targets.category) ==
            {'Furniture', 'Clothing', 'Electronics'}, 'Unexpected categories')
    require(set(details.order_id) == set(orders.order_id), 'Unmatched order IDs')
    require(targets.groupby('category').size().eq(12).all(), 'Incomplete target calendar')
    require(sorted(targets.month.unique()) == list(pd.date_range('2018-04-01', periods=12, freq='MS')),
            'Target months differ from expected April 2018 to March 2019')
    merged = details.merge(orders, on='order_id', how='left', validate='many_to_one',
                           suffixes=('_detail', '_order'), indicator=True)
    require(merged._merge.eq('both').all(), 'Unmatched merge rows')
    merged = merged.drop(columns='_merge')
    require(len(merged) == len(details), 'Merge changed the line count')
    require(merged[['amount', 'profit', 'quantity']].sum().equals(
            details[['amount', 'profit', 'quantity']].sum()), 'Merge inflated totals')
    merged['month'] = merged.order_date.dt.to_period('M').dt.to_timestamp()
    out = {}
    out['category'] = aggregate(merged, ['category'])
    out['subcategory'] = aggregate(merged, ['category', 'subcategory'])
    out['states'] = aggregate(merged, ['state']).sort_values(
        ['orders', 'sales', 'state'], ascending=[False, False, True])
    out['top_states'] = out['states'].head(5)
    out['cities'] = aggregate(merged, ['state', 'city'])
    out['state_category'] = aggregate(merged, ['state', 'category'])
    out['city_category'] = aggregate(merged, ['state', 'city', 'category'])
    out['order_totals'] = aggregate(merged, ['order_id', 'state', 'city'])
    out['category_orders'] = aggregate(merged, ['category', 'order_id'])
    monthly = aggregate(merged, ['month', 'category'])
    target_actual = targets[['month', 'category', 'target']].merge(
        monthly, on=['month', 'category'], how='outer', validate='one_to_one', indicator=True)
    require(target_actual._merge.eq('both').all(), 'Actual/target month mismatch')
    target_actual = target_actual.drop(columns='_merge').sort_values(['category', 'month'])
    target_actual['target_mom_pct'] = target_actual.groupby('category').target.pct_change(fill_method=None) * 100
    target_actual['actual_mom_pct'] = target_actual.groupby('category').sales.pct_change(fill_method=None) * 100
    target_actual['attainment_pct'] = target_actual.sales / target_actual.target * 100
    target_actual['gap'] = target_actual.sales - target_actual.target
    out['monthly'] = target_actual
    out['furniture_monthly'] = target_actual.query("category == 'Furniture'")
    loss = merged.assign(loss_amount=merged.profit.clip(upper=0),
                         loss_line=merged.profit.lt(0).astype(int)).groupby('category').agg(
        loss_lines=('loss_line', 'sum'), gross_losses=('loss_amount', 'sum')).reset_index()
    loss_orders = out['category_orders'].assign(loss_order=lambda x: x.profit.lt(0).astype(int)).groupby('category').loss_order.sum()
    out['category'] = out['category'].merge(loss, on='category')
    out['category']['loss_orders'] = out['category'].category.map(loss_orders)
    out['category']['loss_order_pct'] = 100 * out['category'].loss_orders / out['category'].orders
    # Flag source geography without silently changing the assignment dataset.
    geo_flags = orders.loc[orders.state.eq('Madhya Pradesh') & orders.city.eq('Delhi')].copy()
    geo_flags['reason'] = 'Delhi city recorded under Madhya Pradesh; verify with source owner'
    out['geography_flags'] = geo_flags
    sensitivity = merged.copy()
    sensitivity.loc[sensitivity.order_id.isin(geo_flags.order_id), 'state'] = 'Delhi'
    out['state_sensitivity_delhi'] = aggregate(sensitivity, ['state']).sort_values(
        ['orders', 'sales', 'state'], ascending=[False, False, True])

    # Independent check using plain PDF text and built-in Python, not pandas.
    raw_rows = []
    line_re = re.compile(r'^(B-\d+)\s+(\d+)\s+(-?\d+)\s+(\d+)\s*(Clothing|Electronics|Furniture)\s+(.+)$')
    for page in PdfReader(ROOT / FILES['details']).pages:
        for line in page.extract_text().splitlines():
            if line.startswith('B-'):
                match = line_re.fullmatch(line.strip())
                require(match is not None, f'Independent extraction failed: {line}')
                raw_rows.append(match.groups())
    require(len(raw_rows) == 1500, 'Independent row count failed')
    reference = defaultdict(lambda: {'sales': 0, 'profit': 0, 'ids': set()})
    for oid, amount, profit, units, category, subcategory in raw_rows:
        reference[category]['sales'] += int(amount)
        reference[category]['profit'] += int(profit)
        reference[category]['ids'].add(oid)
    for row in out['category'].itertuples():
        check = reference[row.category]
        require((row.sales, row.profit, row.orders) ==
                (check['sales'], check['profit'], len(check['ids'])), 'Independent category totals fail')
        require(np.isclose(row.profit_per_order, check['profit'] / len(check['ids'])), 'Order average fails')
    for name in ['category', 'subcategory', 'states', 'cities', 'monthly']:
        require(int(out[name].sales.sum()) == int(details.amount.sum()), f'{name} sales reconciliation')
        require(int(out[name].profit.sum()) == int(details.profit.sum()), f'{name} profit reconciliation')
    furn = out['furniture_monthly']
    require(pd.isna(furn.target_mom_pct.iloc[0]), 'First MoM must be missing')
    for prev, curr in zip(furn.itertuples(), list(furn.itertuples())[1:]):
        require(np.isclose(curr.target_mom_pct, 100 * (curr.target - prev.target) / prev.target), 'MoM fails')
    # A zero-denominator result is unavailable, never infinity or fabricated zero.
    require(pd.isna(ratio(pd.Series([1.0]), pd.Series([0.0])).iloc[0]), 'Zero handling fails')
    for kind, frame in zip(FILES, [orders, details, targets]):
        frame.to_csv(DATA / f'{kind}.csv', index=False)
    merged.to_csv(DATA / 'merged.csv', index=False)
    for name, frame in out.items():
        frame.to_csv(TABLES / f'{name}.csv', index=False, float_format='%.10f')
    audit = {
        'status': 'PASS', 'python': sys.version.split()[0],
        'input_hashes': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES.values()},
        'rows': {'orders': len(orders), 'details': len(details), 'targets': len(targets), 'merged': len(merged)},
        'date_range': [str(orders.order_date.min().date()), str(orders.order_date.max().date())],
        'totals': {c: int(details[c].sum()) for c in ['amount', 'profit', 'quantity']},
        'duplicate_detail_rows': int(details.duplicated(COLUMNS['details']).sum()),
        'zero_amount_rows': int(details.amount.eq(0).sum()),
        'negative_profit_lines': int(details.profit.lt(0).sum()),
        'loss_making_orders': int(out['order_totals'].profit.lt(0).sum()),
        'unmatched_ids': 0, 'duplicate_order_ids': 0, 'missing_required_fields': 0,
        'geography_flag_orders': geo_flags.order_id.tolist(),
        'corrections': ['Trimmed surrounding extraction whitespace only; no values recoded or removed.'],
        'preserved_labels': ['Hankerchief', 'Simla', 'Andhra Pradesh / Hyderabad', 'Jammu and Kashmir / Kashmir'],
        'checks': ['every source row width', 'source and joined counts', 'key uniqueness',
                   'date parsing', 'numeric types', 'target calendar', 'missing fields',
                   'referential integrity', 'many-to-one join', 'independent category totals',
                   'all dimensional reconciliations', 'distinct-order means', 'MoM formula', 'zero denominator'],
    }
    (TABLES / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    packages = ['pandas', 'numpy', 'pypdf', 'pdfplumber', 'matplotlib', 'python-docx', 'pillow', 'reportlab', 'pypdfium2']
    (ROOT / 'requirements.txt').write_text('\n'.join(f'{p}=={metadata.version(p)}' for p in packages) + '\n')
    print(json.dumps(audit, indent=2))
    for name in ['category', 'subcategory', 'furniture_monthly', 'top_states', 'cities']:
        print('\n' + name.upper())
        print(out[name].to_string(index=False))


if __name__ == '__main__':
    main()
