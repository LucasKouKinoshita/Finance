#!/usr/bin/env python3
"""fin - controle de gastos financeiros direto no terminal.

Sem dependências externas (apenas biblioteca padrão do Python 3.8+).
Os dados ficam em ./assets/finance.csv (pasta ignorada pelo git).
"""
import argparse
import csv
import os
import sys
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_FILE = ASSETS_DIR / "finance.csv"
FIELDS = ["id", "kind", "month", "date", "description", "category", "amount", "end_month"]

FIXED, VAR, INCOME, BAL = "fixed", "var", "income", "balance"
CENT = Decimal("0.01")
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

try:  # garante acentos/box-drawing em terminais Windows
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(text, code):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else str(text)


def bold(t): return _c(t, "1")
def dim(t): return _c(t, "2")
def red(t): return _c(t, "31")
def green(t): return _c(t, "32")
def cyan(t): return _c(t, "36")


# --------------------------------------------------------------------------
# Utilidades: dinheiro, datas
# --------------------------------------------------------------------------
def brl(v):
    v = Decimal(v).quantize(CENT, ROUND_HALF_UP)
    sign = "-" if v < 0 else ""
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}R$ {s}"


def parse_money(text):
    t = str(text).strip().replace("R$", "").replace(" ", "")
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):          # 1.500,50
            t = t.replace(".", "").replace(",", ".")
        else:                                     # 1,500.50
            t = t.replace(",", "")
    elif "," in t:                                # 1500,50
        t = t.replace(",", ".")
    elif t.count(".") > 1:                        # 1.500.000
        t = t.replace(".", "")
    elif t.count(".") == 1 and len(t.split(".")[1]) == 3:
        raise ValueError(f"valor ambíguo: {text!r} (escreva 1500 ou 1500.00)")
    try:
        v = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"valor inválido: {text!r}")
    if not v.is_finite():
        raise ValueError(f"valor inválido: {text!r}")
    return v.quantize(CENT, ROUND_HALF_UP)


def current_month():
    return date.today().strftime("%Y-%m")


def parse_month(text):
    if text in (None, "current"):
        return current_month()
    t = text.strip()
    try:
        if "/" in t:
            m, y = t.split("/")
        else:
            y, m = t.split("-")
        y, m = int(y), int(m)
        if not (1 <= m <= 12 and 1900 <= y <= 9999):
            raise ValueError
    except ValueError:
        raise ValueError(f"mês inválido: {text!r} (use AAAA-MM ou MM/AAAA)")
    return f"{y:04d}-{m:02d}"


def parse_date(text):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"data inválida: {text!r} (use AAAA-MM-DD ou DD/MM/AAAA)")


def next_month(m):
    y, mo = int(m[:4]), int(m[5:]) + 1
    if mo > 12:
        y, mo = y + 1, 1
    return f"{y:04d}-{mo:02d}"


def month_range(start, end):
    m = start
    while m <= end:
        yield m
        m = next_month(m)


def title(m):
    return f"{MESES[int(m[5:]) - 1]} de {m[:4]}"


def short_date(iso):
    return f"{iso[8:10]}/{iso[5:7]}" if len(iso) >= 10 else iso


# --------------------------------------------------------------------------
# Armazenamento (CSV)
# --------------------------------------------------------------------------
def load():
    if not DATA_FILE.exists():
        return []
    rows = []
    with DATA_FILE.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["id"] = int(r["id"])
            r["amount"] = Decimal(r["amount"])
            rows.append(r)
    return rows


def save(rows):
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["id"]):
            w.writerow({**r, "amount": f"{r['amount']:.2f}"})
    tmp.replace(DATA_FILE)  # escrita atômica


def new_row(rows, kind, **kw):
    r = {"id": max((x["id"] for x in rows), default=0) + 1, "kind": kind,
         "month": "", "date": "", "description": "", "category": "",
         "amount": Decimal(0), "end_month": ""}
    r.update(kw)
    return r


def find_row(rows, rid, kinds):
    for r in rows:
        if r["id"] == rid and r["kind"] in kinds:
            return r
    raise ValueError(f"nenhum registro #{rid} encontrado para essa operação")


# --------------------------------------------------------------------------
# Regras de negócio
# --------------------------------------------------------------------------
def fixed_active(rows, month):
    """Custos fixos vigentes no mês (end_month é exclusivo)."""
    return [r for r in rows if r["kind"] == FIXED and r["month"] <= month
            and (not r["end_month"] or month < r["end_month"])]


def var_of(rows, month):
    return [r for r in rows if r["kind"] == VAR and r["month"] == month]


def bal_of(rows, month):
    return [r for r in rows if r["kind"] == BAL and r["month"] == month]


def income_of(rows, month):
    """Receita vigente: a definida mais recente com início <= mês."""
    cand = [r for r in rows if r["kind"] == INCOME and r["month"] <= month]
    if not cand:
        return Decimal(0)
    return max(cand, key=lambda r: (r["month"], r["id"]))["amount"]


def total(rs):
    return sum((r["amount"] for r in rs), Decimal(0))


def summary(rows, month):
    inc = income_of(rows, month)
    added = total(bal_of(rows, month))
    fixed = total(fixed_active(rows, month))
    var = total(var_of(rows, month))
    return {"income": inc, "added": added, "fixed": fixed, "var": var,
            "expenses": fixed + var, "balance": inc + added - fixed - var}


def months_span(rows):
    if not rows:
        return []
    ms = [r["month"] for r in rows if r["month"]]
    return list(month_range(min(ms), max(max(ms), current_month())))


def accumulated(rows, month):
    ms = [r["month"] for r in rows if r["month"]]
    if not ms or month < min(ms):
        return Decimal(0)
    return sum((summary(rows, m)["balance"] for m in month_range(min(ms), month)), Decimal(0))


# --------------------------------------------------------------------------
# Saída formatada
# --------------------------------------------------------------------------
def heading(text):
    print()
    print(bold(cyan(text)))
    print(dim("═" * len(text)))


def section(text):
    print()
    print(bold(text))


def line(label, v, color=False):
    val = brl(v).rjust(16)
    if color:
        val = green(val) if v > 0 else red(val) if v < 0 else val
    print(f"  {label:<26}{val}")


def table(headers, body, aligns):
    widths = [max([len(h)] + [len(r[i]) for r in body]) for i, h in enumerate(headers)]

    def fmt(cells):
        return "  ".join(f"{c:{aligns[i]}{widths[i]}}" for i, c in enumerate(cells))

    head = fmt(headers)
    print("  " + bold(head))
    print("  " + dim("─" * len(head)))
    for r in body:
        print("  " + fmt(r))


def ok(msg):
    print(green("✔ ") + msg)


def print_summary(s, acc):
    section("Resumo")
    line("Receita", s["income"])
    line("+ Saldo adicionado", s["added"])
    line("− Custos fixos", s["fixed"])
    line("− Custos variáveis", s["var"])
    print("  " + dim("─" * 42))
    line("= Saldo do mês", s["balance"], color=True)
    line("Saldo acumulado", acc, color=True)


# --------------------------------------------------------------------------
# Comandos de escrita: add / rmv / set / edit
# --------------------------------------------------------------------------
def cmd_add(a):
    rows = load()
    if a.fixed_cost:
        desc, val = a.fixed_cost
        amount = parse_money(val)
        if amount <= 0:
            raise ValueError("o valor deve ser maior que zero")
        month = parse_month(a.month)
        r = new_row(rows, FIXED, month=month, date=f"{month}-01", description=desc.strip(),
                    category=(a.cat or "geral").strip(), amount=amount)
        rows.append(r)
        save(rows)
        ok(f"Custo fixo #{r['id']} adicionado: {r['description']} — {brl(amount)}/mês (desde {month})")
    elif a.var_cost:
        desc, val = a.var_cost
        amount = parse_money(val)
        if amount <= 0:
            raise ValueError("o valor deve ser maior que zero")
        d = parse_date(a.date) if a.date else date.today()
        r = new_row(rows, VAR, month=d.strftime("%Y-%m"), date=d.isoformat(),
                    description=desc.strip(), category=(a.cat or "geral").strip(), amount=amount)
        rows.append(r)
        save(rows)
        ok(f"Custo variável #{r['id']} adicionado: {r['description']} — {brl(amount)} em {d:%d/%m/%Y}")
    else:
        amount = parse_money(a.bal)
        if amount == 0:
            raise ValueError("o valor não pode ser zero")
        d = parse_date(a.date) if a.date else date.today()
        r = new_row(rows, BAL, month=d.strftime("%Y-%m"), date=d.isoformat(),
                    description=(a.note or "saldo adicionado").strip(), amount=amount)
        rows.append(r)
        save(rows)
        ok(f"Saldo #{r['id']} registrado: {brl(amount)} em {d:%d/%m/%Y}")


def cmd_rmv(a):
    rows = load()
    for rid, kind in ((a.fixed_cost, FIXED), (a.var_cost, VAR), (a.bal, BAL)):
        if rid is not None:
            break
    r = find_row(rows, rid, (kind,))
    if kind == FIXED:
        month = parse_month(a.month)
        if r["end_month"] and r["end_month"] <= month:
            raise ValueError(f"o custo fixo #{rid} já foi encerrado em {r['end_month']}")
        if month <= r["month"]:
            rows.remove(r)
            save(rows)
            ok(f"Custo fixo #{rid} ({r['description']}) removido por completo")
        else:
            r["end_month"] = month
            save(rows)
            ok(f"Custo fixo #{rid} ({r['description']}) encerrado a partir de {month} "
               f"(meses anteriores preservados)")
    else:
        rows.remove(r)
        save(rows)
        ok(f"Registro #{rid} ({r['description']} — {brl(r['amount'])}) removido")


def cmd_set(a):
    rows = load()
    amount = parse_money(a.inc)
    if amount < 0:
        raise ValueError("a receita não pode ser negativa")
    month = parse_month(a.month)
    same = [r for r in rows if r["kind"] == INCOME and r["month"] == month]
    if same:
        same[0]["amount"] = amount
    else:
        rows.append(new_row(rows, INCOME, month=month, date=f"{month}-01",
                            description="receita mensal", amount=amount))
    save(rows)
    ok(f"Receita mensal definida: {brl(amount)} (a partir de {month}, até nova alteração)")


def cmd_edit(a):
    rows = load()
    r = find_row(rows, a.id, (FIXED, VAR, BAL, INCOME))
    if a.desc is None and a.amount is None and a.cat is None:
        raise ValueError("informe ao menos --desc, --amount ou --cat")
    if a.desc is not None:
        r["description"] = a.desc.strip()
    if a.cat is not None:
        r["category"] = a.cat.strip()
    if a.amount is not None:
        r["amount"] = parse_money(a.amount)
    save(rows)
    ok(f"Registro #{r['id']} atualizado: {r['description']} — {brl(r['amount'])}")


# --------------------------------------------------------------------------
# Comandos de leitura: check
# --------------------------------------------------------------------------
def show_month(rows, month):
    heading(f"Controle financeiro — {title(month)}")
    fixed = sorted(fixed_active(rows, month), key=lambda r: r["id"])
    var = sorted(var_of(rows, month), key=lambda r: (r["date"], r["id"]))
    adds = sorted(bal_of(rows, month), key=lambda r: (r["date"], r["id"]))
    s = summary(rows, month)

    section("Custos fixos")
    if fixed:
        table(["ID", "Descrição", "Categoria", "Valor"],
              [[str(r["id"]), r["description"], r["category"], brl(r["amount"])] for r in fixed], "<<<>")
        line("Total", s["fixed"])
    else:
        print(dim("  (nenhum)"))

    section("Custos variáveis")
    if var:
        table(["ID", "Data", "Descrição", "Categoria", "Valor"],
              [[str(r["id"]), short_date(r["date"]), r["description"], r["category"],
                brl(r["amount"])] for r in var], "<<<<>")
        line("Total", s["var"])
    else:
        print(dim("  (nenhum)"))

    if adds:
        section("Saldo adicionado")
        table(["ID", "Data", "Descrição", "Valor"],
              [[str(r["id"]), short_date(r["date"]), r["description"], brl(r["amount"])]
               for r in adds], "<<<>")
        line("Total", s["added"])

    print_summary(s, accumulated(rows, month))
    if s["income"] == 0:
        print(dim("\n  Dica: defina sua receita com:  fin set --inc VALOR"))


def show_month_bal(rows, month):
    heading(f"Saldo — {title(month)}")
    print_summary(summary(rows, month), accumulated(rows, month))


def show_month_exp(rows, month):
    heading(f"Gastos — {title(month)}")
    s = summary(rows, month)
    line("Custos fixos", s["fixed"])
    line("Custos variáveis", s["var"])
    print("  " + dim("─" * 42))
    line("Total gasto", s["expenses"])
    if s["income"] > 0:
        pct = s["expenses"] / s["income"] * 100
        txt = f"{pct:.1f}% da receita"
        print("  " + (red(txt) if pct > 100 else txt))


def show_cat(rows, month):
    heading(f"Gastos por categoria — {title(month)}")
    agg = {}
    for r in fixed_active(rows, month) + var_of(rows, month):
        key = r["category"] or "geral"
        agg[key] = agg.get(key, Decimal(0)) + r["amount"]
    if not agg:
        print(dim("\n  (sem gastos neste mês)"))
        return
    tot = sum(agg.values(), Decimal(0))
    body = [[k, brl(v), f"{v / tot * 100:.1f}%"]
            for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
    print()
    table(["Categoria", "Total", "%"], body, "<>>")
    line("Total", tot)


def show_total(rows):
    heading("Todos os meses registrados")
    ms = months_span(rows)
    if not ms:
        print(dim("\n  Nenhum registro ainda. Comece com:  fin set --inc 5000"))
        return
    body, acc = [], Decimal(0)
    tot = {k: Decimal(0) for k in ("income", "added", "fixed", "var")}
    for m in ms:
        s = summary(rows, m)
        acc += s["balance"]
        for k in tot:
            tot[k] += s[k]
        body.append([m, brl(s["income"]), brl(s["added"]), brl(s["fixed"]), brl(s["var"]),
                     brl(s["balance"]), brl(acc)])
    print()
    table(["Mês", "Receita", "+ Saldo", "Fixos", "Variáveis", "Saldo", "Acumulado"], body, "<>>>>>>")
    section("Totais")
    line("Receita total", tot["income"])
    line("Saldo adicionado", tot["added"])
    line("Gastos totais", tot["fixed"] + tot["var"])
    line("Saldo final", acc, color=True)


def show_fixed(rows):
    heading("Custos fixos cadastrados")
    fx = sorted((r for r in rows if r["kind"] == FIXED), key=lambda r: r["id"])
    if not fx:
        print(dim("\n  (nenhum)"))
        return
    now = current_month()
    body = []
    for r in fx:
        if r["end_month"] and r["end_month"] <= now:
            status = "encerrado"
        elif r["month"] > now:
            status = "futuro"
        else:
            status = "ativo"
        body.append([str(r["id"]), r["description"], r["category"], brl(r["amount"]),
                     r["month"], r["end_month"] or "—", status])
    print()
    table(["ID", "Descrição", "Categoria", "Valor", "Início", "Fim", "Status"], body, "<<<><<<")


def show_inc(rows):
    heading("Histórico de receita mensal")
    inc = sorted((r for r in rows if r["kind"] == INCOME), key=lambda r: r["month"])
    if not inc:
        print(dim("\n  (não definida) — use:  fin set --inc VALOR"))
        return
    print()
    table(["ID", "Vigente desde", "Valor"],
          [[str(r["id"]), r["month"], brl(r["amount"])] for r in inc], "<<>")
    print()
    line(f"Receita atual ({current_month()})", income_of(rows, current_month()))


def cmd_check(a):
    rows = load()
    shown = False
    if a.month is not None:
        show_month(rows, parse_month(a.month)); shown = True
    if a.total:
        show_total(rows); shown = True
    if a.month_bal is not None:
        show_month_bal(rows, parse_month(a.month_bal)); shown = True
    if a.month_exp is not None:
        show_month_exp(rows, parse_month(a.month_exp)); shown = True
    if a.cat is not None:
        show_cat(rows, parse_month(a.cat)); shown = True
    if a.fixed:
        show_fixed(rows); shown = True
    if a.inc:
        show_inc(rows); shown = True
    if not shown:  # `fin check` sozinho = mês atual
        show_month(rows, current_month())
    print()


def cmd_path(_a):
    print(DATA_FILE)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
EPILOG = """\
exemplos:
  fin set --inc 5000                          define receita mensal
  fin add --fixed-cost "Aluguel" 1500 --cat moradia
  fin add --var-cost "Mercado" 230,50 --cat comida
  fin add --var-cost "Cinema" 45 --date 28/09/2026
  fin add --bal 300 --note "freela"
  fin check --month                           tabela completa do mês atual
  fin check --month 2026-09                   tabela de outro mês
  fin check --total                           todos os meses
  fin check --month-bal                       saldo do mês
  fin check --month-exp                       gastos do mês
  fin rmv --var-cost 7                        remove pelo ID (veja em `check --month`)
  fin rmv --fixed-cost 2 --month 2026-11      encerra custo fixo a partir de nov/2026

valores aceitam: 1500  1500.50  1500,50  1.500,50
"""


def build_parser():
    p = argparse.ArgumentParser(prog="fin", description="Controle de gastos financeiros no terminal.",
                                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", metavar="COMANDO")

    # add
    pa = sub.add_parser("add", help="adiciona custo fixo, custo variável ou saldo")
    g = pa.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixed-cost", nargs=2, metavar=("DESCRICAO", "VALOR"), help="custo fixo (recorrente)")
    g.add_argument("--var-cost", nargs=2, metavar=("DESCRICAO", "VALOR"), help="custo variável (pontual)")
    g.add_argument("--bal", metavar="VALOR", help="saldo adicionado (use valor negativo para retirada)")
    pa.add_argument("--cat", help="categoria (padrão: geral)")
    pa.add_argument("--date", help="data do gasto/saldo (AAAA-MM-DD ou DD/MM/AAAA; padrão: hoje)")
    pa.add_argument("--month", help="mês de início do custo fixo (AAAA-MM; padrão: mês atual)")
    pa.add_argument("--note", help="descrição do saldo adicionado")
    pa.set_defaults(func=cmd_add)

    # rmv
    pr = sub.add_parser("rmv", help="remove custo fixo, custo variável ou saldo pelo ID")
    g = pr.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixed-cost", type=int, metavar="ID")
    g.add_argument("--var-cost", type=int, metavar="ID")
    g.add_argument("--bal", type=int, metavar="ID")
    pr.add_argument("--month", help="custo fixo: mês a partir do qual deixa de valer (padrão: mês atual)")
    pr.set_defaults(func=cmd_rmv)

    # set
    ps = sub.add_parser("set", help="define a receita mensal")
    ps.add_argument("--inc", required=True, metavar="VALOR", help="ganho mensal")
    ps.add_argument("--month", help="vale a partir deste mês (AAAA-MM; padrão: mês atual)")
    ps.set_defaults(func=cmd_set)

    # edit
    pe = sub.add_parser("edit", help="edita descrição, valor ou categoria de um registro")
    pe.add_argument("id", type=int)
    pe.add_argument("--desc")
    pe.add_argument("--amount", metavar="VALOR")
    pe.add_argument("--cat")
    pe.set_defaults(func=cmd_edit)

    # check
    pc = sub.add_parser("check", help="consulta dados (sem flags = mês atual)")
    opt = dict(nargs="?", const="current", metavar="AAAA-MM")
    pc.add_argument("--month", "-month", help="tabela completa do mês", **opt)
    pc.add_argument("--total", "-total", action="store_true", help="todos os meses registrados")
    pc.add_argument("--month-bal", "-month-bal", help="saldo do mês", **opt)
    pc.add_argument("--month-exp", "-month-exp", help="gastos do mês", **opt)
    pc.add_argument("--cat", help="gastos do mês por categoria", **opt)
    pc.add_argument("--fixed", action="store_true", help="lista todos os custos fixos")
    pc.add_argument("--inc", action="store_true", help="histórico da receita mensal")
    pc.set_defaults(func=cmd_check)

    # path
    pp = sub.add_parser("path", help="mostra onde o arquivo CSV está salvo")
    pp.set_defaults(func=cmd_path)
    return p


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        sys.argv[1] = sys.argv[1].lower()  # "Add", "CHECK" também funcionam
    args = build_parser().parse_args()
    try:
        if not args.command:
            show_month(load(), current_month())
            print()
        else:
            args.func(args)
    except ValueError as e:
        print(red(f"Erro: {e}"), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
