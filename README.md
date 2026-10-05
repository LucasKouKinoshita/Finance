# fin — controle de gastos no terminal

CLI em Python 3.8+ (sem dependências). Dados em `assets/finance.csv` (pasta no `.gitignore`).

## Uso

```bash
python3 fin.py --help
# opcional: alias no ~/.bashrc ou ~/.zshrc
alias fin="python3 /caminho/para/controle-gastos/fin.py"
```

| Comando | O que faz |
|---|---|
| `fin set --inc 5000 [--month AAAA-MM]` | Define a receita mensal (vale a partir do mês até nova alteração) |
| `fin add --fixed-cost "Aluguel" 1500 [--cat X] [--month AAAA-MM]` | Custo fixo (recorrente) |
| `fin add --var-cost "Mercado" 230,50 [--cat X] [--date DD/MM/AAAA]` | Custo variável (pontual) |
| `fin add --bal 300 [--note "freela"] [--date ...]` | Adiciona saldo (valor negativo = retirada) |
| `fin rmv --fixed-cost ID [--month AAAA-MM]` | Encerra o custo fixo a partir do mês (histórico preservado) |
| `fin rmv --var-cost ID` / `fin rmv --bal ID` | Remove o registro |
| `fin edit ID [--desc ..] [--amount ..] [--cat ..]` | Edita um registro |
| `fin check --month [AAAA-MM]` | Tabela completa do mês |
| `fin check --total` | Todos os meses registrados |
| `fin check --month-bal [AAAA-MM]` | Saldo do mês (+ acumulado) |
| `fin check --month-exp [AAAA-MM]` | Gasto do mês (+ % da receita) |
| `fin check --cat [AAAA-MM]` | Gastos por categoria |
| `fin check --fixed` | Lista todos os custos fixos |
| `fin check --inc` | Histórico de receita |
| `fin path` | Mostra onde está o CSV |

`fin` sem argumentos mostra o mês atual. Comandos aceitam maiúsculas (`Add`, `Check`).

## Regras

- **Saldo do mês** = receita + saldo adicionado − custos fixos − custos variáveis
- **Saldo acumulado** = soma dos saldos de todos os meses até o mês consultado
- Valores aceitos: `1500`, `1500.50`, `1500,50`, `1.500,50`
- Os IDs aparecem em `fin check --month`
