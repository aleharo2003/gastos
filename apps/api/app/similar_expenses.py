"""Similitud explicable entre descripciones; no usa importes ni categorias."""
import re
from app.expense_search import normalize, sound_key, near

STOP_WORDS = frozenset('de del la el los las en con y por para un una pago pagar compra compras'.split())


def terms(description):
    return set(word for word in re.findall(r'[a-z0-9]+',normalize(description))
               if word not in STOP_WORDS and any(c.isalpha() for c in word))


def same_word(left,right):
    if left == right:
        return True
    if min(len(left),len(right)) < 4:
        return False
    return sound_key(left)==sound_key(right) or near(left,right,2 if min(len(left),len(right))>=8 else 1)


def similarity(left,right):
    """0 sin coincidencia, 1 descripcion igual normalizada, 2 descripcion parecida."""
    if normalize(left) == normalize(right):
        return 1
    left,right=sorted(terms(left)),sorted(terms(right))
    if not left or not right:
        return 0
    # Emparejamiento uno a uno: una palabra no justifica varias coincidencias.
    edges=[[j for j,word in enumerate(right) if same_word(term,word)] for term in left]
    assigned={}
    def assign(index,seen):
        for target in edges[index]:
            if target in seen:
                continue
            seen.add(target)
            if target not in assigned or assign(assigned[target],seen):
                assigned[target]=index
                return True
        return False
    matches=sum(assign(i,set()) for i in range(len(left)))
    shorter,longer=sorted((len(left),len(right)))
    return 2 if matches*3 >= shorter*2 and matches*2 >= longer else 0
