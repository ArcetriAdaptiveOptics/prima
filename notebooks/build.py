"""Build the course notebooks from ``notebooks/src/*.py``.

Source format ("percent" cells)::

    # %% [markdown]
    # testo in *markdown* (ogni riga commentata con '# ')
    # %%
    codice comune
    # %% [esercizio]
    scheletro per gli studenti (solo nella versione esercizi)
    # %% [soluzione]
    soluzione (solo nella versione soluzioni)

Output: ``notebooks/NN-name.ipynb`` (esercizi) and
``notebooks/soluzioni/NN-name.ipynb``.

    python notebooks/build.py                 # all
    python notebooks/build.py 03 --execute    # build + run the solutions
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import nbformat

HERE = Path(__file__).resolve().parent
CELL = re.compile(r'^# %%(?: \[(\w+)\])?\s*$')


def parse(src: str):
    cells, kind, buf = [], None, []
    for line in src.splitlines():
        m = CELL.match(line)
        if m:
            if kind is not None:
                cells.append((kind, buf))
            kind, buf = (m.group(1) or 'code'), []
        elif kind is not None:
            buf.append(line)
    if kind is not None:
        cells.append((kind, buf))
    return cells


def to_nb(cells, solutions: bool):
    nb = nbformat.v4.new_notebook()
    nb.metadata['kernelspec'] = {'name': 'python3', 'display_name':
                                 'Python 3', 'language': 'python'}
    nb.metadata['language_info'] = {'name': 'python'}
    for kind, lines in cells:
        if kind == ('esercizio' if solutions else 'soluzione'):
            continue
        text = '\n'.join(lines).strip('\n')
        if kind == 'markdown':
            text = '\n'.join(re.sub(r'^# ?', '', ln) for ln in lines)
            nb.cells.append(nbformat.v4.new_markdown_cell(text.strip('\n')))
        else:
            c = nbformat.v4.new_code_cell(text)
            if kind in ('esercizio', 'soluzione'):
                c.metadata['tags'] = [kind]
            nb.cells.append(c)
    return nb


def build(src: Path, execute: bool = False, timeout: int = 1800):
    cells = parse(src.read_text())
    name = src.stem.replace('_', '-')
    out_ex = HERE / (name + '.ipynb')
    out_sol = HERE / 'soluzioni' / (name + '.ipynb')
    out_sol.parent.mkdir(exist_ok=True)
    nbformat.write(to_nb(cells, False), out_ex)
    sol = to_nb(cells, True)
    nbformat.write(sol, out_sol)
    print('built', out_ex.relative_to(HERE), '+',
          out_sol.relative_to(HERE))
    if execute:
        from nbconvert.preprocessors import ExecutePreprocessor
        ep = ExecutePreprocessor(timeout=timeout, kernel_name='python3')
        ep.preprocess(sol, {'metadata': {'path': str(HERE / 'soluzioni')}})
        run = HERE / 'soluzioni' / '_eseguiti' / (name + '.ipynb')
        run.parent.mkdir(exist_ok=True)
        nbformat.write(sol, run)
        print('executed ->', run.relative_to(HERE))
    return out_ex, out_sol


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('which', nargs='*', help='prefix, e.g. 03')
    ap.add_argument('--execute', action='store_true')
    a = ap.parse_args(argv)
    srcs = sorted((HERE / 'src').glob('*.py'))
    if a.which:
        srcs = [s for s in srcs if any(s.name.startswith(w)
                                       for w in a.which)]
    for s in srcs:
        build(s, a.execute)


if __name__ == '__main__':
    sys.exit(main())
