from migrations import v001_inicial, v002_ideias_impressao

MIGRACOES = [
    (1, "Estrutura inicial das 16 tabelas e índices", v001_inicial.aplicar),
    (2, "Tabela de notas e ideias de impressão 3D com análise de marketplace e fatiamento", v002_ideias_impressao.aplicar),
]
