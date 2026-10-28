"""Intercambio verificable con Losas.exe, sin sustituir su salida por el motor PM.

Contrato DL y TXT de F. Perdomo; referencia de interoperabilidad:
EstructurasRD, DLFileService / SalidaPerdomoAdapter (MIT).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from puente_losas.dl_io import MomentosTxt, SistemaDL, cargar_dl, leer_txt


@dataclass(frozen=True)
class CasoLegacy:
    dl: Path
    txt: Path
    mapa: Path
    manifiesto: Path
    advertencias: tuple[str, ...]


def preparar_legacy(origen: str | Path, raiz: str | Path | None = None,
                    marcas: dict[int, str] | None = None) -> CasoLegacy:
    """Copia inmutable a un nombre 8.3 bajo una ruta corta, con identidad por hash.

    La copia es byte por byte: esta operación no cambia cargas ni geometría.
    No ejecuta Losas.exe ni afirma que exista un TXT válido de esa corrida.
    """
    origen = Path(origen).resolve()
    datos = origen.read_bytes()
    sistema = cargar_dl(str(origen))
    ids = {l.id for l in sistema.losas}
    marcas = marcas or {i: str(i) for i in ids}
    if set(marcas) != ids or any(not str(v).strip() for v in marcas.values()):
        raise ValueError('El mapa de marcas debe cubrir exactamente las losas del DL.')
    marca_json = {str(k): str(v) for k, v in sorted(marcas.items())}
    digest = hashlib.sha256(datos).hexdigest()
    clave = hashlib.sha256(datos + json.dumps(marca_json, sort_keys=True).encode()).hexdigest()
    carpeta = (Path(raiz) if raiz is not None else Path.home()/'LosasRD')/clave[:8].upper()
    carpeta.mkdir(parents=True, exist_ok=True)
    dl = carpeta/'SISTEMA.DL'
    manifiesto = carpeta/'CASO.json'
    if dl.exists() and dl.read_bytes() != datos:
        raise FileExistsError(f'La copia corta fue editada; no se sobrescribe: {dl}')
    if manifiesto.exists():
        previo = json.loads(manifiesto.read_text(encoding='utf-8'))
        if previo.get('clave') != clave:
            raise FileExistsError(f'Colisión de identidad en {carpeta}')
    if not dl.exists():
        with dl.open('xb') as f:
            f.write(datos)
    avisos = []
    if len(str(dl.resolve())) > 80:
        avisos.append('Ruta de ejecución mayor de 80 caracteres; elegir una raíz más corta.')
    if not str(dl.resolve()).isascii() or any(c.isspace() for c in str(dl.resolve())):
        avisos.append('Ruta con espacios o caracteres no ASCII; elegir una raíz simple.')
    mapa = carpeta/'MAPA.csv'
    with mapa.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'mark'])
        writer.writerows(sorted(marcas.items()))
    manifiesto.write_text(json.dumps({
        'origen': str(origen), 'dl': str(dl.resolve()), 'txt': str(dl.with_suffix('.TXT').resolve()),
        'sha256_dl': digest, 'clave': clave, 'marcas': marca_json,
        'advertencias': avisos, 'estado': 'preparado; ejecución externa pendiente',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    return CasoLegacy(dl, dl.with_suffix('.TXT'), mapa, manifiesto, tuple(avisos))


@dataclass(frozen=True)
class ArmaduraNativa:
    losa: int
    losa_j: int | None
    direccion: str
    d_cm: float
    mu_tm_m: float
    as_cm2_m: float | None
    as_provista_cm2_m: float | None
    disponer: str
    insuficiente: bool
    mu_i: float | None = None
    mu_j: float | None = None
    as_i_cm2_m: float | None = None
    as_j_cm2_m: float | None = None
    as_adicional_cm2_m: float | None = None


@dataclass(frozen=True)
class ReporteNativo:
    momentos: list[MomentosTxt]
    armaduras: list[ArmaduraNativa]
    texto: str

    def a_dict(self) -> dict:
        return {'fuente': 'Losas.exe / TXT', 'momentos': [asdict(m) for m in self.momentos],
                'armaduras': [asdict(a) for a in self.armaduras]}


_NUM = r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))'
_VANO = re.compile(r'^\s*(\d+)\s+' + r'\s+'.join([_NUM]*3) + r'\s+(.+?)\s*$')
_APOYO = re.compile(r'^\s*(\d+)\s*-\s*(\d+)\s+' + r'\s+'.join([_NUM]*8) + r'\s+(.+?)\s*$')
_ULTIMO_NUMERO = re.compile(r'^(.*?)\s+' + _NUM + r'\s*$')


def _normalizar(texto: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', texto.upper())
                   if unicodedata.category(c) != 'Mn')


def leer_reporte(texto: str, sistema: SistemaDL | None = None) -> ReporteNativo:
    """Lee momentos, armaduras de vano y de apoyo, incluyendo fallos As > As max.

    Si se entrega el DL, exige correspondencia de entradas y tablas completas.
    Un cero usado por el EXE para señalar una sección insuficiente se vuelve None.
    """
    momentos, _ = leer_txt(texto)
    armaduras = []
    direccion = None
    apoyo = False
    for linea in texto.splitlines():
        normal = _normalizar(linea)
        if 'ARMADURAS SEGUN' in normal:
            direccion = 'X' if '"X"' in normal else 'Y' if '"Y"' in normal else None
            apoyo = 'SOBRE LOS APOYOS' in normal
            continue
        if not direccion:
            continue
        match = (_APOYO if apoyo else _VANO).match(linea)
        if not match:
            continue
        g = match.groups()
        if apoyo:
            i, j = int(g[0]), int(g[1])
            mi, mj, mu, d, area, ai, aj, adicional = map(float, g[2:10])
            disponer = g[10].strip()
            provista = None
        else:
            i, j = int(g[0]), None
            d, mu, area = map(float, g[1:4])
            disponer = g[4].strip()
            tail = _ULTIMO_NUMERO.match(disponer)
            disponer, provista = (tail[1].strip(), float(tail[2])) if tail else (disponer, None)
            mi = mj = ai = aj = adicional = None
        fallo = 'AS>ASMAX' in _normalizar(disponer).replace(' ', '')
        armaduras.append(ArmaduraNativa(i, j, direccion, d, mu, None if fallo else area,
                                        None if fallo else provista, disponer, fallo,
                                        mi, mj, ai, aj, None if fallo else adicional))
    report = ReporteNativo(momentos, armaduras, texto)
    if sistema is not None:
        _validar_reporte(report, sistema)
    return report


def _validar_reporte(reporte: ReporteNativo, sistema: SistemaDL) -> None:
    entradas = {l.id: l for l in sistema.losas}
    if len(entradas) != len(sistema.losas) or {m.losa for m in reporte.momentos} != set(entradas):
        raise ValueError('La salida no cubre las losas de entrada.')
    if len(reporte.momentos) != len(entradas):
        raise ValueError('Momentos duplicados en la salida.')
    for m in reporte.momentos:
        l = entradas[m.losa]
        # Losas.exe imprime 0 en la luz que no participa en un voladizo.
        lx_ok = abs(m.lx-l.lx) <= .00051 or (l.tipo == 71 and m.lx == 0)
        ly_ok = abs(m.ly-l.ly) <= .00051 or (l.tipo == 72 and m.ly == 0)
        if (m.tipo != l.tipo or abs(m.carga-l.carga) > .00051 or
                abs(m.h_cm-l.espesor*100) > .0501 or not lx_ok or not ly_ok):
            raise ValueError(f'La salida corresponde a otra entrada: losa {m.losa}.')
    esperado = {(i, None, d) for i in entradas for d in ('X', 'Y')}
    esperado |= {(i, j, 'X') for i, j, _ in sistema.pares_x}
    esperado |= {(i, j, 'Y') for i, j, _ in sistema.pares_y}
    actual = [(a.losa, a.losa_j, a.direccion) for a in reporte.armaduras]
    if set(actual) != esperado or len(actual) != len(esperado):
        raise ValueError('Tabla de armaduras incompleta, duplicada o de otra entrada.')


def barras_por_nervio(as_cm2_m: float | None, paso_m: float, area_barra_mm2: float) -> int | None:
    """Conversión aritmética As/m × paso; no verifica la sección del nervio."""
    if as_cm2_m is None:
        return None
    if not all(math.isfinite(v) for v in (as_cm2_m, paso_m, area_barra_mm2)):
        raise ValueError('As, paso y área deben ser finitos.')
    if as_cm2_m < 0 or paso_m <= 0 or area_barra_mm2 <= 0:
        raise ValueError('As no negativa, paso y área positivos requeridos.')
    cantidad = Decimal(str(as_cm2_m))*100*Decimal(str(paso_m))/Decimal(str(area_barra_mm2))
    return int(cantidad.to_integral_value(rounding=ROUND_CEILING))


def main(argv=None):
    """Preparar DL corto, importar TXT completo o rellenar copia XLSM explícita."""
    import argparse
    from puente_losas.plantilla_xlsm import escribir_copia_xlsm
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='accion', required=True)
    prep = sub.add_parser('preparar')
    prep.add_argument('--dl', required=True)
    prep.add_argument('--ruta-corta')
    prep.add_argument('--mapa', help='CSV id,mark')
    imp = sub.add_parser('importar')
    imp.add_argument('--dl', required=True)
    imp.add_argument('--txt', required=True)
    imp.add_argument('--salida', required=True)
    plant = sub.add_parser('plantilla')
    plant.add_argument('--origen', required=True)
    plant.add_argument('--salida', required=True)
    plant.add_argument('--entradas', required=True, help='JSON {hoja:{celda:valor}}, sin fórmulas')
    args = p.parse_args(argv)
    if args.accion == 'preparar':
        marcas = None
        if args.mapa:
            with open(args.mapa, encoding='utf-8-sig', newline='') as f:
                filas = list(csv.DictReader(f))
            marcas = {int(r['id']): r['mark'] for r in filas}
            if len(marcas) != len(filas):
                raise ValueError('IDs duplicados en mapa')
        caso = preparar_legacy(args.dl, args.ruta_corta, marcas)
        print(caso.manifiesto.read_text(encoding='utf-8'))
    elif args.accion == 'importar':
        dl, txt = Path(args.dl), Path(args.txt)
        report = leer_reporte(txt.read_text(encoding='cp1252'), cargar_dl(str(dl)))
        data = report.a_dict()
        data.update(sha256_dl=hashlib.sha256(dl.read_bytes()).hexdigest(),
                    sha256_txt=hashlib.sha256(txt.read_bytes()).hexdigest())
        with Path(args.salida).open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(args.salida)
    else:
        entradas = json.loads(Path(args.entradas).read_text(encoding='utf-8-sig'))
        print(escribir_copia_xlsm(args.origen, args.salida, entradas))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
