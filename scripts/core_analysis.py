"""Compact, independently runnable calculation appendix. Inputs: data/*.csv."""
from pathlib import Path
import pandas as pd
import numpy as np

root = Path(__file__).resolve().parents[1]
orders = pd.read_csv(root / 'data/orders.csv', parse_dates=['order_date'])
lines = pd.read_csv(root / 'data/details.csv')
targets = pd.read_csv(root / 'data/targets.csv', parse_dates=['month'])
assert orders.order_id.is_unique
assert set(lines.order_id) == set(orders.order_id)
joined = lines.merge(orders, on='order_id', validate='many_to_one')
assert len(joined) == len(lines) == 1500
assert joined.amount.sum() == lines.amount.sum()
assert joined.profit.sum() == lines.profit.sum()
joined['month'] = joined.order_date.dt.to_period('M').dt.to_timestamp()


def summarize(keys):
    result = joined.groupby(keys).agg(
        sales=('amount', 'sum'), profit=('profit', 'sum'),
        orders=('order_id', 'nunique'), lines=('order_id', 'size'))
    result['profit_per_order'] = result.profit / result.orders
    result['margin_pct'] = 100 * result.profit / result.sales.replace(0, np.nan)
    return result.reset_index()


categories = summarize(['category'])
subcategories = summarize(['category', 'subcategory'])
states = summarize(['state']).sort_values(
    ['orders', 'sales', 'state'], ascending=[False, False, True])
cities = summarize(['state', 'city'])
months = summarize(['month', 'category'])
monthly = targets.merge(months, on=['month', 'category'],
                        how='outer', validate='one_to_one', indicator=True)
assert monthly._merge.eq('both').all()
monthly = monthly.sort_values(['category', 'month'])
monthly['target_mom_pct'] = (
    monthly.groupby('category').target.pct_change(fill_method=None) * 100)
monthly['attainment_pct'] = monthly.sales / monthly.target * 100
monthly['gap'] = monthly.sales - monthly.target
furniture = monthly.loc[monthly.category.eq('Furniture')]

# Same answers as the full pipeline, including distinct-order denominators.
expected = pd.read_csv(root / 'analysis/category.csv').set_index('category')
actual = categories.set_index('category')
for field in ['sales', 'profit', 'orders', 'profit_per_order', 'margin_pct']:
    assert np.allclose(actual[field], expected.loc[actual.index, field])
for frame in [categories, subcategories, states, cities, months]:
    assert frame.sales.sum() == lines.amount.sum()
    assert frame.profit.sum() == lines.profit.sum()
assert pd.isna(furniture.target_mom_pct.iloc[0])

for title, result in [('Categories', categories), ('Top states', states.head(5)),
                      ('Furniture targets', furniture)]:
    print(title)
    print(result.to_string(index=False))
