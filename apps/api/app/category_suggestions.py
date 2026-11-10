"""Sugerencias explicables a partir del historial autorizado de una cuenta."""
from collections import Counter
from app.expense_search import ExpenseSearch, normalize

EMPTY = {'categoria':None, 'coincidencias':0, 'total':0}


def suggest_category(description, rows):
    query = normalize(description)
    if len(query) < 4 or not any(c.isalpha() for c in query):
        return dict(EMPTY)
    search = ExpenseSearch(description)
    levels = {3:Counter(), 2:Counter(), 1:Counter()}
    for row in rows:
        category = row['categoria']
        if category is None:
            continue
        if normalize(row['descripcion']) == query:
            level = 3
        else:
            match = search.match(row['descripcion'])
            if not match:
                continue
            level = 2 if match == 1 else 1
        levels[level][category] += 1
    # Preferir evidencia exacta aunque la aproximada sea mas abundante.
    counts = next((levels[level] for level in (3,2,1) if levels[level]), Counter())
    if not counts:
        return dict(EMPTY)
    category, count = counts.most_common(1)[0]
    total = sum(counts.values())
    if count < 2 or count * 3 < total * 2:
        return dict(EMPTY)
    return {'categoria':category, 'coincidencias':count, 'total':total}
