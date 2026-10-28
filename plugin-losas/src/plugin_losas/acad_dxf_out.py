"""Planos DXF GR editables, con contorno original y espesor con procedencia.

Reutiliza el contrato del flujo AutoCAD/Excel de la Ing. Arlette Ramirez.
No dibuja un bbox ni decide espesores o armaduras.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import math
from pathlib import Path

from plugin_losas.acad_dxf import _area_poligono, _punto_en_poligono
from plugin_losas.extraccion import FilaLosa

CONTORNOS = 'GR_LOSAS_CONTORNO'
ROTULOS = 'GR_LOSAS_ROTULOS'
APPID = 'GR_LOSAS'


def _cadena(s):
    if not isinstance(s,str) or not s.strip() or any(ord(c)<32 for c in s):
        raise ValueError('Texto vacio o con caracteres de control en el DXF')
    if len(s.encode('cp1252'))>200:
        raise ValueError('Texto DXF mayor de 200 bytes')
    return s


@dataclass(frozen=True)
class EspesorRotulo:
    h_m: float | None
    origen: str
    estado: str = 'calculado'
    h_modelo_m: float | None = None

    def __post_init__(self):
        if self.estado not in ('calculado','fijado','pendiente'):
            raise ValueError('Estado de espesor desconocido')
        for h in (self.h_m,self.h_modelo_m):
            if h is not None and (type(h) not in (int,float) or not math.isfinite(h) or h<=0):
                raise ValueError('Espesor positivo y finito requerido')
        if self.h_m is None and self.estado!='pendiente':
            raise ValueError('Espesor sin valor: estado pendiente requerido')
        if self.h_m is not None:
            _cadena(self.origen)

    def texto(self):
        if self.h_m is None:
            return 'h pendiente'
        if self.estado=='pendiente':
            other=f' / DL={self.h_modelo_m*100:g} cm' if self.h_modelo_m is not None else ''
            return f'h Excel={self.h_m*100:g} cm{other}\\Ppor conciliar'
        origen=self.origen.replace('\\','\\\\').replace('{','\\{').replace('}','\\}')
        return f'h={self.h_m*100:g} cm\\P{origen}'


def _orient(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _cruzan(a,b,c,d):
    def on(p,q,r):
        return abs(_orient(p,q,r))<1e-12 and min(p[0],q[0])-1e-12<=r[0]<=max(p[0],q[0])+1e-12 and min(p[1],q[1])-1e-12<=r[1]<=max(p[1],q[1])+1e-12
    o1,o2,o3,o4=_orient(a,b,c),_orient(a,b,d),_orient(c,d,a),_orient(c,d,b)
    return o1*o2<0 and o3*o4<0 or any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b)))


def _poligono(contorno):
    pts=tuple(tuple(float(v) for v in p) for p in contorno)
    if len(pts)>3 and pts[0]==pts[-1]:pts=pts[:-1]
    if len(pts)<3 or any(len(p)!=2 or not all(math.isfinite(x) for x in p) for p in pts):
        raise ValueError('Se requiere contorno original finito de al menos tres vertices')
    if _area_poligono(pts)<1e-10:
        raise ValueError('Contorno sin area')
    n=len(pts)
    for i in range(n):
        if pts[i]==pts[(i+1)%n]:raise ValueError('Vertices consecutivos repetidos')
        for j in range(i+1,n):
            if j==i+1 or i==0 and j==n-1:continue
            if _cruzan(pts[i],pts[(i+1)%n],pts[j],pts[(j+1)%n]):
                raise ValueError('Contorno con autointersecciones')
    return pts


def _interior(pts):
    """Centro de un intervalo interior; funciona tambien con un poligono en L."""
    ys=sorted(set(p[1] for p in pts));center=(ys[0]+ys[-1])/2
    levels=[center]+[(a+b)/2 for a,b in zip(ys,ys[1:])]
    candidates=[]
    for y in levels:
        xs=[]
        for a,b in zip(pts,pts[1:]+pts[:1]):
            if (a[1]>y)!=(b[1]>y):xs.append(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        xs.sort()
        for lo,hi in zip(xs[::2],xs[1::2]):
            p=((lo+hi)/2,y)
            if hi>lo and _punto_en_poligono(*p,pts):candidates.append((hi-lo,-abs(y-center),p))
    if not candidates:raise ValueError('No se encontro un punto interior para el rotulo')
    return max(candidates)[2]


def escribir_dxf(filas: list[FilaLosa], espesores: dict[str,EspesorRotulo] | None = None,
                 *, unidad='mm', desplazamiento_m=(0.,0.), altura_texto_m=.18) -> str:
    """DXF R2000/cp1252. Geometria de entrada en m; traslado solo si es explicito."""
    import ezdxf
    if unidad not in ('m','mm'):raise ValueError('Unidad DXF: m o mm')
    if len(desplazamiento_m)!=2 or not all(math.isfinite(x) for x in desplazamiento_m):
        raise ValueError('Traslacion XY finita requerida')
    if not math.isfinite(altura_texto_m) or altura_texto_m<=0:
        raise ValueError('Altura de texto positiva requerida')
    if not filas or len({f.mark for f in filas})!=len(filas):
        raise ValueError('Lista vacia o marcas duplicadas')
    if len({f.nivel for f in filas})>1:
        raise ValueError('Exportar un nivel por archivo; indique --nivel')
    factor=1000 if unidad=='mm' else 1
    doc=ezdxf.new('R2000',units=4 if unidad=='mm' else 6)
    doc.appids.new(APPID)
    doc.layers.new(CONTORNOS,dxfattribs={'color':3})
    doc.layers.new(ROTULOS,dxfattribs={'color':2})
    space=doc.modelspace();espesores=espesores or {}
    for f in filas:
        _cadena(f.mark)
        pts=_poligono(f.contorno)
        dx,dy=desplazamiento_m
        pts=tuple((x+dx,y+dy) for x,y in pts)
        position=_interior(pts);height=altura_texto_m*factor
        esp=espesores.get(f.mark,EspesorRotulo(None,'','pendiente'))
        values=['marca:'+f.mark,'estado:'+esp.estado]
        if f.nivel:values.append('nivel:'+_cadena(f.nivel))
        if f.revit_id is not None:values.append('id_revit:'+str(f.revit_id))
        if esp.origen:values.append('origen:'+_cadena(esp.origen))
        if esp.h_m is not None and esp.estado!='pendiente':values.append('h_m:'+repr(esp.h_m))
        if esp.h_m is not None and esp.estado=='pendiente':values.append('h_candidato_m:'+repr(esp.h_m))
        if esp.h_modelo_m is not None:values.append('h_referencia_m:'+repr(esp.h_modelo_m))
        poly=space.add_lwpolyline([(x*factor,y*factor) for x,y in pts],close=True,dxfattribs={'layer':CONTORNOS})
        poly.set_xdata(APPID,[(1000,'rol:contorno')]+[(1000,v) for v in values])
        mark=space.add_text(f.mark,dxfattribs={'layer':ROTULOS,'height':height,
                                             'insert':(position[0]*factor,position[1]*factor)})
        mark.set_xdata(APPID,[(1000,'rol:marca')]+[(1000,v) for v in values])
        width=max(max(x for x,y in pts)-min(x for x,y in pts),altura_texto_m*4)*.8*factor
        text=space.add_mtext(esp.texto(),dxfattribs={'layer':ROTULOS,'char_height':height*.7,'width':width})
        text.set_location((position[0]*factor,position[1]*factor-height*1.8),attachment_point=5)
        text.set_xdata(APPID,[(1000,'rol:espesor')]+[(1000,v) for v in values])
    buffer=StringIO();doc.write(buffer);result=buffer.getvalue()
    result.encode('cp1252')
    return result


def guardar_dxf(texto: str,ruta: str | Path):
    """Salida nueva; no reemplaza DWG ni DXF existentes."""
    if Path(ruta).suffix.lower()!='.dxf':
        raise ValueError('La salida debe tener extension .dxf; no es un archivo DWG')
    data=texto.replace('\r\n','\n').replace('\n','\r\n').encode('cp1252')
    with Path(ruta).open('xb') as f:f.write(data)
