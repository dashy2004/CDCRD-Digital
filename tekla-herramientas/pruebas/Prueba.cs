using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.Serialization.Json;
using CDCRD.Tekla;

internal class Prueba
{
    public static int Main()
    {
        var dir = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), "inventario-" + Guid.NewGuid().ToString("N")));
        try
        {
            string destino = Path.Combine(dir.FullName, "seleccion.json");
            string conjunto = "20000000-0000-0000-0000-000000000001";
            var a = new Pieza { guid = "10000000-0000-0000-0000-000000000001", conjunto_guid = conjunto,
                perfil = "PL10", material = "Acero sintético", marca = "P-1" };
            var b = new Pieza { guid = "10000000-0000-0000-0000-000000000002",
                conjunto_guid = "20000000-0000-0000-0000-000000000002", perfil = "PL12", material = "Acero sintético" };
            var piezas = new List<Pieza> {a,b};
            var dibujos = new List<PlanoConjunto> {new PlanoConjunto { conjunto_guid = conjunto, marca = "A-001", estado_de_actualizacion = "Test" }};
            var informe = Inventario.Crear("Ejemplo", piezas, dibujos, 1);
            informe.Exportar(destino);
            using(var archivo = File.OpenRead(destino))
            {
                var copia = (Inventario)new DataContractJsonSerializer(typeof(Inventario)).ReadObject(archivo);
                if(copia.piezas.Count != 2 || copia.planos_de_conjunto.Count != 1 || copia.seleccion_omitida != 1 ||
                   copia.piezas[0].material != a.material || copia.piezas[0].conjunto_guid != copia.planos_de_conjunto[0].conjunto_guid)
                    throw new Exception("No coincide el cruce por GUID ni el recuento.");
            }
            try { informe.Exportar(destino); throw new Exception("Sobrescritura."); } catch(IOException) {}
            try { Inventario.Crear("Ejemplo", new List<Pieza>(), dibujos, 0); throw new Exception("Selección vacía."); }
            catch(ArgumentException) {}
            if(dir.GetFiles().Length != 1) throw new Exception("Archivos parciales.");
            Console.WriteLine("OK: selección, relación de plano por GUID, conjunto sin plano, JSON UTF-8 y destino protegido.");
            return 0;
        }
        finally { dir.Delete(true); }
    }
}
