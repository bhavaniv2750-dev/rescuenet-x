import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, numpy as np
NAVY, TEAL = '#14304f', '#0e7490'
plt.rcParams.update({'font.size': 7, 'axes.edgecolor': '#5b6878', 'axes.spines.top': False, 'axes.spines.right': False})
def sv(fig, n): fig.savefig(f'fig/{n}.png', dpi=220, facecolor='white', bbox_inches='tight'); plt.close(fig)

# confusion matrices (real values from the served model's evaluation record)
fig, axs = plt.subplots(1, 2, figsize=(6.2, 2.7))
for ax, cm, t in [(axs[0], [[153, 4], [2, 41]], 'Stratified hold-out (200 records)'), (axs[1], [[160, 1], [4, 35]], 'Chronological hold-out (200 records)')]:
    ax.imshow(cm, cmap='GnBu', vmin=0, vmax=170)
    for i in range(2):
        for j in range(2): ax.text(j, i, cm[i][j], ha='center', va='center', fontsize=11, fontweight='bold', color='white' if cm[i][j] > 100 else NAVY)
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1]); ax.set_xticklabels(['No flood', 'Flood']); ax.set_yticklabels(['No flood', 'Flood']); ax.set_xlabel('Predicted'); ax.set_ylabel('Actual'); ax.set_title(t, fontsize=7, color=NAVY)
    for s in ax.spines.values(): s.set_visible(False)
sv(fig, 'f_cm')

# evaluation suite
fig, ax = plt.subplots(figsize=(6.2, 2.6))
names = ['All four inputs\n(label leakage)', 'Weather only\n(served model)', 'Weather + noisy\ngauge (sd 0.5 m)', 'Next-hour\nforecast']; acc = [100.0, 97.5, 97.5, 61.6]; col = ['#b9c4cf', TEAL, '#6fb7c8', '#e0a458']
b = ax.bar(names, acc, color=col, width=0.55)
for r, v in zip(b, acc): ax.text(r.get_x() + r.get_width() / 2, v + 1.5, f'{v:.1f}%', ha='center', fontsize=7, fontweight='bold', color=NAVY)
ax.set_ylim(0, 112); ax.set_ylabel('Accuracy (%)'); ax.axhline(50, color='#999', lw=0.6, ls='--'); ax.text(3.45, 51.5, 'chance level', fontsize=6, color='#777', ha='right')
sv(fig, 'f_suite')

# feature importance
fig, ax = plt.subplots(figsize=(6.2, 1.9))
f = ['Rainfall (mm/h)', 'Humidity (%)', 'Temperature (C)']; v = [88.2, 6.1, 5.8]
ax.barh(f[::-1], v[::-1], color=TEAL, height=0.5)
for i, x in enumerate(v[::-1]): ax.text(x + 1, i, f'{x:.1f}%', va='center', fontsize=7, fontweight='bold', color=NAVY)
ax.set_xlim(0, 100); ax.set_xlabel('Gini feature importance (%) of the served Random Forest')
sv(fig, 'f_imp')

# vision
fig, ax = plt.subplots(figsize=(6.2, 2.4))
labels = ['Flood detection rate\n(809 flood photos)', 'False alarms\n(300 non-flood photos)', 'Precision\n(combined)', 'Specificity\n(combined)']; vals = [99.3, 7.3, 97.3, 92.7]; cs = [TEAL, '#e0a458', TEAL, TEAL]
bb = ax.bar(labels, vals, color=cs, width=0.5)
for r, x in zip(bb, vals): ax.text(r.get_x() + r.get_width() / 2, x + 2, f'{x}%', ha='center', fontsize=7, fontweight='bold', color=NAVY)
ax.set_ylim(0, 115); ax.set_ylabel('Percent')
sv(fig, 'f_vis_eval')

# tests
fig, ax = plt.subplots(figsize=(6.2, 2.4))
t = ['Complete backend suite', 'P0 dispatch safety', 'Private media + public refs', 'Invitations, agencies,\nbootstrap', 'Workspaces, endpoint auth,\nmigrations', 'Frontend unit / component\n+ regression']
n = [782, 66, 53, 69, 52, 61]
ax.barh(t[::-1], n[::-1], color=TEAL, height=0.55)
for i, x in enumerate(n[::-1]): ax.text(x + 8, i, str(x), va='center', fontsize=7, fontweight='bold', color=NAVY)
ax.set_xlim(0, 900); ax.set_xlabel('Tests passed (the backend count includes the other rows)')
sv(fig, 'f_tests')
print('ok')
