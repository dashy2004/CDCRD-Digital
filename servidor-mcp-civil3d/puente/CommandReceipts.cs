using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;

namespace Cdcrd.Civil3dBridge
{
    // Pure state machine. CAD work never runs under this lock or on a socket thread.
    internal sealed class CommandReceipts
    {
        private sealed class Entry
        {
            public string Id, Document, Command, State="encolado", Error;
            public long Created;
            public List<string> Events=new List<string>();
        }
        private readonly object gate=new object();
        private readonly Dictionary<string,Entry> entries=new Dictionary<string,Entry>();
        private readonly Func<long> clock;
        private readonly long queueTimeout;
        public CommandReceipts(Func<long> clock=null,long queueTimeout=60000)
        {
            this.clock=clock ?? (()=>(long)(Stopwatch.GetTimestamp()*1000d/Stopwatch.Frequency));
            this.queueTimeout=queueTimeout;
        }
        private void Expire()
        {
            foreach(var e in entries.Values.Where(e=>e.State=="encolado" && clock()-e.Created>=queueTimeout))
            { e.State="cancelado";e.Error="Vencio antes de ejecutar; el despachador no ejecutara este ticket."; }
        }
        public string Add(string document,string command)
        {
            lock(gate)
            {
                Expire();
                if(entries.Values.Any(e=>e.Document==document && (e.State=="encolado" || e.State=="en_ejecucion")))
                    throw new InvalidOperationException("Ya hay un comando seguido pendiente en este documento.");
                foreach(var old in entries.Values.Where(e=>e.State!="encolado" && e.State!="en_ejecucion")
                    .OrderBy(e=>e.Created).Take(Math.Max(0,entries.Count-127)).ToArray()) entries.Remove(old.Id);
                if(entries.Count>=128)throw new InvalidOperationException("Demasiados comandos activos.");
                var entry=new Entry{Id=Guid.NewGuid().ToString("N"),Document=document,Command=command,Created=clock()};
                entries.Add(entry.Id,entry);return entry.Id;
            }
        }
        public bool Start(string id)
        {
            lock(gate) { Expire();if(!entries.TryGetValue(id,out var e)||e.State!="encolado")return false;e.State="en_ejecucion";return true; }
        }
        public bool Active(string id)
        {
            lock(gate) { Expire();return entries.TryGetValue(id,out var e) && (e.State=="encolado" || e.State=="en_ejecucion"); }
        }
        public void Event(string id,string value)
        {
            lock(gate) { if(entries.TryGetValue(id,out var e)&&e.Events.Count<128)e.Events.Add(value); }
        }
        public void Finish(string id,string state,string error=null)
        {
            if(!new[]{"terminado","fallido","cancelado","desconocido"}.Contains(state))throw new ArgumentException("Estado final invalido.");
            lock(gate)
            {
                if(entries.TryGetValue(id,out var e)&&(e.State=="encolado"||e.State=="en_ejecucion"))
                {e.State=state;e.Error=error;}
            }
        }
        public object Get(string id)
        {
            lock(gate)
            {
                Expire();
                if(!entries.TryGetValue(id,out var e))throw new ArgumentException("Ticket inexistente o fuera del historial de esta sesion.");
                return new Dictionary<string,object>{{"ticket",id},{"dibujo",e.Document},{"comando",e.Command},
                    {"estado",e.State},{"finalizado",e.State!="encolado"&&e.State!="en_ejecucion"},
                    {"correcto",e.State=="terminado"},{"error",e.Error},{"eventos",e.Events.ToArray()},
                    {"nota","CommandEnded confirma fin del comando, no valida su resultado geometrico. No reintentar un comando en ejecucion."}};
            }
        }
    }
}
