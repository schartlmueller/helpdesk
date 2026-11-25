"""Diagramme der Übersicht als SVG. Ohne Django, einzeln testbar.

Die Zahlen werden hier zu fertigen Koordinaten gerechnet, damit die deutsche
Zahlenformatierung der Vorlagen kein Komma in die Grafik schreibt. Farben und
Schrift kommen aus der CSS-Datei (Klassen ``viz-...``).
"""

from html import escape

WIDTH = 760
LEFT, RIGHT, TOP, BOTTOM = 40, 46, 14, 26


def _n(value):
    return f"{value:.1f}"


def _nice_max(value):
    """Rundet das Achsenmaximum auf eine glatte Zahl mit vier gleichen Schritten."""
    if value <= 4:
        return 4
    for step in (2, 3, 5, 10, 15, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000):
        if step * 4 >= value:
            return step * 4
    return int(value * 1.2) + 1


def _frame(height, top_value):
    """Waagrechte Hilfslinien mit Beschriftung; gibt (SVG-Teile, y-Funktion) zurück."""
    plot_height = height - TOP - BOTTOM

    def y(value):
        return TOP + plot_height * (1 - value / top_value)

    parts = []
    for i in range(5):
        value = top_value * i / 4
        css = "viz-axis" if i == 0 else "viz-grid"
        parts.append(
            f'<line class="{css}" x1="{LEFT}" x2="{WIDTH - RIGHT}" y1="{_n(y(value))}" y2="{_n(y(value))}"/>'
        )
        parts.append(
            f'<text class="viz-tick" x="{LEFT - 6}" y="{_n(y(value) + 4)}" text-anchor="end">{int(value)}</text>'
        )
    return parts, y


def _x_labels(labels, centers, height, every):
    parts = []
    last = len(labels) - 1
    for index, label in enumerate(labels):
        # Erste, letzte und jede n-te Beschriftung; die vorletzten bleiben frei,
        # damit sich nichts überlappt.
        if index == last or (index % every == 0 and last - index >= every * 0.7):
            parts.append(
                f'<text class="viz-tick" x="{_n(centers[index])}" y="{height - 8}" text-anchor="middle">{escape(label)}</text>'
            )
    return parts


def _hits(centers, band, height, tips):
    """Unsichtbare Flächen je Zeitabschnitt für Fadenkreuz und Hinweisfenster."""
    parts = []
    for center, tip in zip(centers, tips):
        parts.append(
            f'<rect class="viz-hit" x="{_n(center - band / 2)}" y="{TOP}" width="{_n(band)}" '
            f'height="{height - TOP - BOTTOM}" data-x="{_n(center)}" data-tip="{escape(tip, quote=True)}"/>'
        )
    return parts


def _svg(height, parts, label):
    return (
        f'<svg class="viz" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{escape(label, quote=True)}">'
        f'<line class="viz-cross" x1="0" x2="0" y1="{TOP}" y2="{height - BOTTOM}"/>'
        + "".join(parts)
        + "</svg>"
    )


def line_chart(labels, values, tips, label, height=230):
    """Eine Linie über die Zeit, der letzte Wert ist direkt beschriftet."""
    count = len(values)
    if count == 0:
        return ""
    top_value = _nice_max(max(values))
    parts, y = _frame(height, top_value)
    plot_width = WIDTH - LEFT - RIGHT
    band = plot_width / count
    centers = [LEFT + band * (i + 0.5) for i in range(count)]

    points = " ".join(f"{_n(x)},{_n(y(v))}" for x, v in zip(centers, values))
    parts.append(f'<polyline class="viz-line" points="{points}"/>')
    parts.append(
        f'<circle class="viz-dot" cx="{_n(centers[-1])}" cy="{_n(y(values[-1]))}" r="4"/>'
    )
    parts.append(
        f'<text class="viz-value" x="{_n(centers[-1] + 9)}" y="{_n(y(values[-1]) + 4)}">{values[-1]}</text>'
    )
    parts += _x_labels(labels, centers, height, max(1, round(count / 6)))
    parts += _hits(centers, band, height, tips)
    return _svg(height, parts, label)


def _bar(x, y_top, width, y_base):
    """Säule mit abgerundetem oberen Ende und geradem Fuß auf der Grundlinie."""
    height = y_base - y_top
    if height <= 0:
        return ""
    radius = min(4, width / 2, height)
    return (
        f"M{_n(x)},{_n(y_base)} V{_n(y_top + radius)} Q{_n(x)},{_n(y_top)} {_n(x + radius)},{_n(y_top)} "
        f"H{_n(x + width - radius)} Q{_n(x + width)},{_n(y_top)} {_n(x + width)},{_n(y_top + radius)} "
        f"V{_n(y_base)} Z"
    )


def bar_chart(labels, first, second, tips, label, height=190):
    """Zwei Reihen als Säulenpaare nebeneinander (z. B. neu und erledigt)."""
    count = len(labels)
    if count == 0:
        return ""
    top_value = _nice_max(max(first + second))
    parts, y = _frame(height, top_value)
    plot_width = WIDTH - LEFT - RIGHT
    band = plot_width / count
    centers = [LEFT + band * (i + 0.5) for i in range(count)]
    gap = 2
    bar_width = max(2.0, min(24.0, (band - gap) * 0.36))
    base = y(0)

    for center, a, b in zip(centers, first, second):
        path_a = _bar(center - gap / 2 - bar_width, y(a), bar_width, base)
        path_b = _bar(center + gap / 2, y(b), bar_width, base)
        if path_a:
            parts.append(f'<path class="viz-bar viz-s1" d="{path_a}"/>')
        if path_b:
            parts.append(f'<path class="viz-bar viz-s2" d="{path_b}"/>')
    parts += _x_labels(labels, centers, height, max(1, round(count / 6)))
    parts += _hits(centers, band, height, tips)
    return _svg(height, parts, label)
