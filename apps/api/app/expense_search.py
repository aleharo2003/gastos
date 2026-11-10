"""Busqueda determinista en descripciones; no cambia datos ni usa servicios externos."""
import re
import unicodedata
from functools import lru_cache


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize('NFKD', value.casefold())
    return ' '.join(''.join(c for c in decomposed if not unicodedata.combining(c)).split())


def sound_key(word: str) -> str:
    # Variantes acotadas de escritura espanola (incluye seseo).
    return re.sub(r'c(?=[ei])', 's', word).replace('z', 's').replace('v', 'b')


def near(left: str, right: str, limit: int) -> bool:
    """Distancia OSA: insercion, borrado, reemplazo o transposicion adyacente."""
    if abs(len(left)-len(right)) > limit:
        return False
    previous = list(range(len(right)+1))
    before_previous = None
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            value = min(previous[j]+1, current[j-1]+1, previous[j-1]+(a != b))
            if i > 1 and j > 1 and a == right[j-2] and left[i-2] == b:
                value = min(value, before_previous[j-2]+1)
            current.append(value)
        before_previous, previous = previous, current
    return previous[-1] <= limit


class ExpenseSearch:
    """0 = sin coincidencia; 1 = texto contenido; 2 = coincidencia aproximada."""
    def __init__(self, query: str, approximate: bool = True):
        self.query = normalize(query)
        # Signos y comodines se buscan literalmente, nunca como expresiones.
        self.terms = self.query.split() if approximate and re.fullmatch(r'[a-z0-9]+(?: [a-z0-9]+)*', self.query) else []
        # Cache acotada por consulta: no guarda vocabulario entre usuarios.
        self.word_matches = lru_cache(maxsize=512)(self._word_matches)

    @staticmethod
    def _word_matches(term: str, word: str) -> bool:
        if term == word or (len(term) >= 3 and term in word):
            return True
        # Numeros y palabras cortas deben coincidir sin correcciones.
        if len(term) < 4 or not term.isalpha() or not word.isalpha():
            return False
        if sound_key(term) == sound_key(word):
            return True
        return near(term, word, 2 if len(term) >= 8 else 1)

    def match(self, description: str) -> int:
        description = normalize(description)
        if not self.query:
            return 0
        if self.query in description:
            return 1
        if not self.terms:
            return 0
        words = re.findall(r'[a-z0-9]+', description)
        return 2 if all(any(self.word_matches(term, word) for word in words) for term in self.terms) else 0
