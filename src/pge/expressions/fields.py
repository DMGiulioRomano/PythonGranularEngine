"""
fields.py

I campi YAML in cui un'espressione vale come valore (issue #308).

Un letterale in un modulo che non importa niente: chi legge il motore dal
sorgente (un language server, un editor) lo trova qui, e sa dove una stringa
fra parentesi che nomina una mappa e' un valore e dove resta un errore.

Ogni voce e' il path YAML dentro lo stream. La lista si allunga una fetta
alla volta: ogni campo che entra ha i suoi test su unita' di misura e casi
speciali (le altre con la #313).
"""

EXPRESSION_FIELDS = ('grain.duration',)
