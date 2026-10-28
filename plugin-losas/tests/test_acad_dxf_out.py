"""Contrato DXF de ida/vuelta con geometria y datos ficticios."""
from dataclasses import replace
from io import StringIO
import math

import ezdxf
import pytest

from plugin_losas.acad_dxf import leer_entidades, losas_desde_dxf
from plugin_losas.acad_dxf_out import EspesorRotulo, escribir_dxf, guardar_dxf
from plugin_losas.extraccion import FilaLosa


def fila(mark='LA0', contorno=((0.,0.),(5.,0.),(5.,6.),(0.,6.))):
    return FilaLosa(mark, 'Nivel ficticio', 5.,6.,30.,.99,'revit',revit_id=123,contorno=contorno)


@pytest.mark.parametrize('unidad,escala', [('mm',.001),('m',1.)])
def test_roundtrip_identidad_geometria_y_fuente(unidad,escala):
    f=fila('LØ0');text=escribir_dxf([f],{'LØ0':EspesorRotulo(.2,'calculo ficticio Ø')},unidad=unidad)
    text.encode('cp1252')
    doc=ezdxf.read(StringIO(text));assert doc.header['$INSUNITS']==(4 if unidad=='mm' else 6)
    assert not doc.audit().has_errors
    assert {'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS'} <= set(t.dxf.name for t in doc.layers)
    rows,warnings=losas_desde_dxf(text,'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=escala)
    assert not warnings and len(rows)==1
    out=rows[0];assert out.mark==f.mark and out.contorno==f.contorno
    assert (out.lx,out.ly,out.espesor_m,out.revit_id)==(5.,6.,.2,123)
    assert out.criterio_espesor=='calculo ficticio Ø' and out.nivel==f.nivel
    from plugin_losas.acad_dxf import export_para_puente
    assert export_para_puente(rows)['losas'][0]['revit_id']==123


@pytest.mark.parametrize('pts', [((0,0),(4,0),(4,1),(1,1),(1,4),(0,4)),
                                ((2,0),(4,2),(2,4),(0,2))])
def test_contorno_concavo_o_rotado_no_se_sustituye_por_bbox(pts):
    f=fila(contorno=pts);text=escribir_dxf([f]);ents=leer_entidades(text)
    poly=next(e for e in ents if e.tipo=='LWPOLYLINE')
    assert poly.puntos==tuple((x*1000,y*1000) for x,y in pts)
    rows,_=losas_desde_dxf(text,'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    assert rows[0].mark==f.mark and rows[0].contorno==pts


def test_sin_fuente_o_en_conflicto_no_inventa_espesor():
    pending=EspesorRotulo(.33,'Excel ficticio','pendiente',.2)
    text=escribir_dxf([fila()],{'LA0':pending})
    assert 'por conciliar' in text and '33' in text and '20' in text
    rows,_=losas_desde_dxf(text,'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    assert rows[0].espesor_m is None
    assert rows[0].espesor_candidato_m==.33 and rows[0].espesor_referencia_m==.2
    text=escribir_dxf([fila()]);assert 'h pendiente' in text
    rows,_=losas_desde_dxf(text,'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    assert rows[0].espesor_m is None
    from plugin_losas.acad_dxf import export_para_puente
    with pytest.raises(ValueError,match='pendiente'):export_para_puente(rows)
    with pytest.raises(ValueError):EspesorRotulo(.2,'')


def test_geometria_invalida_no_genera_contorno_inventado():
    for pts in [(),((0,0),(2,2),(0,2),(2,0)),((0,0),(1,0),(math.nan,2))]:
        with pytest.raises(ValueError):escribir_dxf([fila(contorno=pts)])
    with pytest.raises(ValueError):escribir_dxf([fila(),fila()])
    with pytest.raises(ValueError):escribir_dxf([fila(),replace(fila('LB0'),nivel='otro')])


def test_traslacion_explicita_y_escritura_no_sobrescribe(tmp_path):
    text=escribir_dxf([fila()],desplazamiento_m=(10.,20.))
    rows,_=losas_desde_dxf(text,'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    assert rows[0].contorno[0]==(10.,20.)
    p=tmp_path/'plano.dxf';guardar_dxf(text,p)
    assert b'\r\n' in p.read_bytes() and not p.read_bytes().startswith(b'\xef\xbb\xbf')
    with pytest.raises(FileExistsError):guardar_dxf(text,p)
    with pytest.raises(ValueError,match='extension'):guardar_dxf(text,tmp_path/'plano.dwg')


@pytest.mark.parametrize('caso',['arco','ocs'])
def test_arcos_y_ocs_no_se_convierten_silenciosamente(caso):
    text=escribir_dxf([fila()]);doc=ezdxf.read(StringIO(text))
    poly=doc.modelspace().query('LWPOLYLINE').first
    if caso=='arco':poly.set_points([(0,0,.5),(5000,0,0),(5000,6000,0),(0,6000,0)],format='xyb')
    else:poly.dxf.extrusion=(0,0,-1)
    buffer=StringIO();doc.write(buffer)
    with pytest.raises(ValueError,match='arcos|OCS'):losas_desde_dxf(buffer.getvalue(),'GR_LOSAS_CONTORNO')


def test_cli_nivel_origen_y_reimportacion(tmp_path):
    import json
    from plugin_losas.cli import main
    records=[{'mark':m,'nivel':n,'revit_id':i,'lx':5,'ly':6,'contorno':fila().contorno,
              'espesor':{'h_usado':.99}} for m,n,i in [('LA0','N1',123),('LB0','N2',124)]]
    src=tmp_path/'p.json';src.write_text(json.dumps({'meta':{'traslacion_origen_mm':[10000,20000]},'losas':records}),encoding='utf-8')
    h=tmp_path/'h.json';h.write_text(json.dumps({'LA0':{'h_m':.2,'origen':'calculo ficticio'}}),encoding='utf-8')
    dst=tmp_path/'salida.dxf'
    assert main(['dxf-salida','--proyecto',str(src),'--salida',str(dst)])==1
    assert not dst.exists()
    args=['dxf-salida','--proyecto',str(src),'--nivel','N1','--espesores',str(h),'--usar-origen-modelo','--salida',str(dst)]
    assert main(args)==0
    rows,_=losas_desde_dxf(dst.read_text(encoding='cp1252'),'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    assert len(rows)==1 and rows[0].contorno[0]==(10.,20.) and rows[0].espesor_m==.2
    assert main(args)==1
    other=tmp_path/'copia.dxf'
    assert main(['dxf-salida','--dxf',str(dst),'--salida',str(other)])==0
    copied,_=losas_desde_dxf(other.read_text(encoding='cp1252'),'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    assert copied==rows


def test_cli_conserva_conflicto_al_reexportar_dxf(tmp_path):
    from plugin_losas.cli import main
    src=tmp_path/'input.dxf';dst=tmp_path/'output.dxf'
    guardar_dxf(escribir_dxf([fila()],{'LA0':EspesorRotulo(.33,'Excel ficticio','pendiente',.2)}),src)
    assert main(['dxf-salida','--dxf',str(src),'--salida',str(dst)])==0
    before,_=losas_desde_dxf(src.read_text(encoding='cp1252'),'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    after,_=losas_desde_dxf(dst.read_text(encoding='cp1252'),'GR_LOSAS_CONTORNO','GR_LOSAS_ROTULOS',escala_a_m=.001)
    assert after==before and after[0].espesor_m is None
