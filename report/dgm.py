"""Tiny diagram toolkit on matplotlib (boxes, arrows, lifelines) so every report figure is generated from code."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Ellipse, FancyArrowPatch, Rectangle, Polygon, Circle

NAVY, TEAL, GREY, LIGHT, PALE, WARN, OK, RED = '#14304f', '#0e7490', '#5b6878', '#eef3f8', '#e3f1f5', '#fdf3dc', '#e3f4ea', '#c0392b'
W = 100.0

def canvas(h, width_in=6.3):
    fig = plt.figure(figsize=(width_in, width_in * h / W))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, h); ax.axis('off'); return fig, ax

def box(ax, x, y, w, h, text='', fc=LIGHT, ec=NAVY, fs=6.2, bold=False, color='#111', r=1.2, lw=0.9, ha='center', va='center', ls='-', z=2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f'round,pad=0,rounding_size={r}', fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))
    if text:
        tx = x + w / 2 if ha == 'center' else x + 1.2
        ax.text(tx, y + h / 2 if va == 'center' else y + h - 1.2, text, ha=ha, va=va, fontsize=fs, fontweight='bold' if bold else 'normal', color=color, zorder=z + 1, linespacing=1.25)

def arrow(ax, p, q, label='', color=NAVY, ls='-', fs=5.2, lw=0.9, off=(0, 1.0), style='-|>', rad=0.0, ha='center', z=1):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=7, lw=lw, color=color, ls=ls, connectionstyle=f'arc3,rad={rad}', zorder=z))
    if label:
        ax.text((p[0] + q[0]) / 2 + off[0], (p[1] + q[1]) / 2 + off[1], label, fontsize=fs, ha=ha, va='center', color=color, zorder=5,
                bbox=dict(fc='white', ec='none', pad=0.6, alpha=0.9))

def title(ax, h, text):
    ax.text(W / 2, h - 2.2, text, ha='center', va='center', fontsize=7.5, fontweight='bold', color=NAVY)

def save(fig, name):
    fig.savefig(f'fig/{name}.png', dpi=220, facecolor='white'); plt.close(fig)

def ellipse(ax, cx, cy, w, h, text, fc=PALE, ec=TEAL, fs=5.6):
    ax.add_patch(Ellipse((cx, cy), w, h, fc=fc, ec=ec, lw=0.9, zorder=2)); ax.text(cx, cy, text, ha='center', va='center', fontsize=fs, zorder=3, linespacing=1.2)

def actor(ax, x, y, label, fs=5.8, s=1.0):
    ax.add_patch(Circle((x, y + 4.2 * s), 1.2 * s, fc='white', ec=NAVY, lw=0.9, zorder=3))
    for (a, b) in [((x, y + 3.0 * s), (x, y + 0.8 * s)), ((x - 1.8 * s, y + 2.2 * s), (x + 1.8 * s, y + 2.2 * s)), ((x, y + 0.8 * s), (x - 1.5 * s, y - 1.2 * s)), ((x, y + 0.8 * s), (x + 1.5 * s, y - 1.2 * s))]:
        ax.plot([a[0], b[0]], [a[1], b[1]], color=NAVY, lw=0.9, zorder=3)
    ax.text(x, y - 2.8 * s, label, ha='center', va='top', fontsize=fs, color='#111', linespacing=1.15)
