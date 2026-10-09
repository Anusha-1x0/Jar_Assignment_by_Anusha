"""Generate reproducible publication charts from analysis CSVs."""
from pathlib import Path
import os
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1] / 'tmp' / 'matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets' / 'charts'
OUT.mkdir(parents=True, exist_ok=True)
INK, PURPLE, TEAL, LOSS = '#243044', '#60429B', '#168477', '#B84734'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                     'svg.fonttype': 'none',
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.spines.left': False, 'axes.spines.bottom': False,
                     'axes.labelcolor': INK, 'text.color': INK,
                     'xtick.color': INK, 'ytick.color': INK,
                     'figure.facecolor': 'white', 'axes.facecolor': 'white'})


def save(fig, name):
    fig.savefig(OUT / f'{name}.png', dpi=260, bbox_inches='tight', facecolor='white')
    fig.savefig(OUT / f'{name}.svg', bbox_inches='tight', facecolor='white')
    plt.close(fig)


def main():
    c = pd.read_csv(ROOT / 'analysis/category.csv').set_index('category').loc[
        ['Electronics', 'Clothing', 'Furniture']]
    fig, axes = plt.subplots(1, 2, figsize=(9.3, 2.4), gridspec_kw={'width_ratios': [1.6, 1]})
    colors = [PURPLE, TEAL, LOSS]
    y = np.arange(3)
    axes[0].barh(y, c.sales / 1000, color=colors, height=.48)
    axes[0].set_yticks(y, c.index)
    axes[0].set_xlim(0, 197)
    axes[0].set_xlabel('Sales (INR thousand)')
    for i, v in enumerate(c.sales): axes[0].text(v/1000+3, i, f'{v:,.0f}', va='center', fontsize=10)
    axes[1].barh(y, c.margin_pct, color=colors, height=.48)
    axes[1].set_yticks(y, [])
    axes[1].set_xlim(0, 10.7)
    axes[1].set_xlabel('Profit margin (%)')
    for i, v in enumerate(c.margin_pct): axes[1].text(v+.15, i, f'{v:.2f}%', va='center')
    for ax in axes:
        ax.invert_yaxis();ax.tick_params(length=0);ax.grid(axis='x', alpha=.15);ax.set_axisbelow(True)
    fig.tight_layout(w_pad=2)
    save(fig, 'category')

    sub = pd.read_csv(ROOT / 'analysis/subcategory.csv').sort_values('profit')
    fig, ax = plt.subplots(figsize=(9.3, 4.0))
    ax.barh(sub.subcategory, sub.profit, color=[LOSS if x < 0 else TEAL for x in sub.profit], height=.64)
    ax.axvline(0, color=INK, lw=.65)
    ax.set_xlim(-5300, 7500)
    for i, v in enumerate(sub.profit):
        ax.text(v+110 if v>=0 else v-110, i, f'{v:,.0f}', ha='left' if v>=0 else 'right', va='center', fontsize=9)
    ax.set_xlabel('Reported profit (INR)');ax.tick_params(length=0)
    ax.grid(axis='x', alpha=.13);ax.set_axisbelow(True)
    fig.tight_layout();save(fig, 'subcategory')

    f = pd.read_csv(ROOT / 'analysis/furniture_monthly.csv', parse_dates=['month'])
    x = np.arange(len(f));labels=f.month.dt.strftime('%b')
    fig, ax = plt.subplots(figsize=(9.3, 2.2))
    ax.plot(x, f.sales/1000, color=PURPLE, marker='o', lw=2, label='Actual sales')
    ax.plot(x, f.target/1000, color=INK, ls='--', lw=1.5, label='Sales target')
    ax.set_xticks(x, labels);ax.set_ylim(0, 25);ax.set_yticks([0,5,10,15,20,25])
    ax.set_ylabel('INR thousand');ax.legend(loc='upper left', frameon=False, ncol=2)
    ax.tick_params(length=0);ax.grid(axis='y', alpha=.15)
    ax.annotate('32.25% attainment', (3, f.sales.iloc[3]/1000), xytext=(2.3,.2), fontsize=9, color=LOSS)
    ax.annotate('184.84%', (9, f.sales.iloc[9]/1000), xytext=(9.1,22.5), fontsize=9, color=PURPLE)
    fig.tight_layout();save(fig, 'furniture_actual')

    fig, ax = plt.subplots(figsize=(9.3, 1.65))
    ax.bar(x[1:], f.target_mom_pct.iloc[1:], color=[PURPLE if i in [3,7,11] else '#BAB0D2' for i in range(1,12)], width=.58)
    for i,v in enumerate(f.target_mom_pct):
        if pd.notna(v): ax.text(i,v+.04,f'{v:.2f}%',ha='center',fontsize=8)
    ax.set_xticks(x,labels);ax.set_ylim(0,2.2);ax.set_yticks([0,1,2]);ax.set_ylabel('Target MoM (%)')
    ax.text(0,.18,'N/A',ha='center',fontsize=8);ax.tick_params(length=0)
    fig.tight_layout();save(fig, 'furniture_mom')

    s=pd.read_csv(ROOT/'analysis/top_states.csv')
    fig, axes=plt.subplots(1,2,figsize=(9.3,2.7),gridspec_kw={'width_ratios':[1.45,1]})
    y=np.arange(5)
    axes[0].barh(y,s.sales/1000,color=PURPLE,height=.55)
    axes[0].set_yticks(y,s.state);axes[0].set_xlim(0,128);axes[0].set_xlabel('Sales (INR thousand)')
    for i,v in enumerate(s.sales):axes[0].text(v/1000+2,i,f'{v/1000:.1f}',va='center',fontsize=9)
    axes[1].barh(y,s.margin_pct,color=[TEAL if p>=0 else LOSS for p in s.profit],height=.55)
    axes[1].set_yticks(y,[]);axes[1].set_xlim(-5.8,9.3);axes[1].set_xlabel('Profit margin (%)');axes[1].axvline(0,color=INK,lw=.6)
    for i,v in enumerate(s.margin_pct):axes[1].text(v+.18 if v>=0 else v-.18,i,f'{v:.2f}%',va='center',ha='left' if v>=0 else 'right',fontsize=9)
    for ax in axes:ax.invert_yaxis();ax.tick_params(length=0);ax.grid(axis='x',alpha=.12);ax.set_axisbelow(True)
    fig.tight_layout();save(fig,'regions')
    print('Five charts created with PNG and editable SVG copies.')


if __name__ == '__main__':
    main()
