// CDCRD-Digital - puente MCP para Civil 3D 2027
// Escucha JSON-RPC por linea en 127.0.0.1 y ejecuta cada peticion en el hilo
// de la aplicacion. Carga por ApplicationPlugins (no requiere NETLOAD).
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
// Autodesk.AutoCAD.Runtime define su propia Exception: sin este alias,
// cualquier catch (Exception) es ambiguo (CS0104).
using Exception = System.Exception;

namespace Cdcrd.Civil3dBridge
{
    public class BridgeApp : IExtensionApplication
    {
        public void Initialize()
        {
            Log.Write("Initialize: el plugin cargo en el proceso de Civil 3D");
            try
            {
                HiloPrincipal.Suscribir();
                BridgeServer.Instance.Start(silent: true);
            }
            catch (Exception ex)
            {
                Log.Write("Initialize fallo: " + ex.Message);
            }
        }

        public void Terminate()
        {
            try { HiloPrincipal.Desuscribir(); } catch { }
            try { BridgeServer.Instance.Stop(silent: true); } catch { }
        }
    }

    public class BridgeCommands
    {
        [CommandMethod("CDCRDMCP", CommandFlags.Session)]
        public static void StartCmd() { HiloPrincipal.Suscribir(); BridgeServer.Instance.Start(silent: false); }

        [CommandMethod("CDCRDMCPSTOP", CommandFlags.Session)]
        public static void StopCmd() { BridgeServer.Instance.Stop(silent: false); }

        [CommandMethod("CDCRDMCPINFO", CommandFlags.Session)]
        public static void InfoCmd()
        {
            var ed = AcApp.DocumentManager.MdiActiveDocument?.Editor;
            string msg = string.Format(
                "\nCDCRD puente Civil 3D: {0}  puerto {1}  escritura {2}  comandos {3}\nlog: {4}\n",
                BridgeServer.Instance.Running ? "activo" : "detenido",
                BridgeServer.Port,
                BridgeServer.AllowWrite ? "si" : "no",
                BridgeServer.AllowCommands ? "si" : "no",
                Log.Path);
            if (ed != null) ed.WriteMessage(msg); else Log.Write(msg);
        }
    }

    internal static class Log
    {
        public static readonly string Path = System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "CdcrdCivil3dBridge", "puente.log");
        private static readonly object Gate = new object();

        public static void Write(string msg)
        {
            try
            {
                lock (Gate)
                {
                    Directory.CreateDirectory(System.IO.Path.GetDirectoryName(Path));
                    var fi = new FileInfo(Path);
                    if (fi.Exists && fi.Length > 4 * 1024 * 1024)
                        File.Move(Path, Path + ".1", true);
                    File.AppendAllText(Path,
                        DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + "  " + msg + Environment.NewLine,
                        new UTF8Encoding(false));
                }
            }
            catch { }
        }
    }

    internal sealed class BridgeServer
    {
        public static readonly BridgeServer Instance = new BridgeServer();

        public static int Port
        {
            get
            {
                int p;
                if (int.TryParse(Environment.GetEnvironmentVariable("CDCRD_C3D_PORT"), out p) && p > 0 && p < 65536)
                    return p;
                return 8760;
            }
        }

        // La escritura esta habilitada por defecto, pero cada llamada sigue exigiendo
        // token de aprobacion. CDCRD_C3D_SOLO_LECTURA=1 la apaga del todo.
        public static bool AllowWrite
        {
            get { return Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") != "1"; }
        }

        // Ejecutar comandos arbitrarios de la linea de comandos esta apagado por defecto.
        public static bool AllowCommands
        {
            get { return Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") == "1"; }
        }

        public static int TimeoutMs
        {
            get
            {
                int t;
                if (int.TryParse(Environment.GetEnvironmentVariable("CDCRD_C3D_TIMEOUT_MS"), out t) && t >= 5000)
                    return t;
                return 55000;
            }
        }

        private TcpListener _listener;
        private Thread _thread;
        private volatile bool _stop;
        public bool Running { get { return _listener != null; } }

        public void Start(bool silent)
        {
            if (Running)
            {
                if (!silent) Say("puente ya activo en el puerto " + Port);
                return;
            }
            _stop = false;
            _listener = new TcpListener(IPAddress.Loopback, Port);
            _listener.Start();
            _thread = new Thread(Loop);
            _thread.IsBackground = true;
            _thread.Name = "cdcrd-c3d-bridge";
            _thread.Start();
            Log.Write("puente iniciado en 127.0.0.1:" + Port);
            if (!silent) Say("puente CDCRD activo en 127.0.0.1:" + Port);
        }

        public void Stop(bool silent)
        {
            _stop = true;
            try { if (_listener != null) _listener.Stop(); } catch { }
            _listener = null;
            Log.Write("puente detenido");
            if (!silent) Say("puente CDCRD detenido");
        }

        private static void Say(string msg)
        {
            var ed = AcApp.DocumentManager.MdiActiveDocument?.Editor;
            if (ed != null) ed.WriteMessage("\n[CDCRD] " + msg + "\n");
        }

        private void Loop()
        {
            while (!_stop)
            {
                TcpClient client = null;
                try
                {
                    client = _listener.AcceptTcpClient();
                }
                catch
                {
                    if (_stop) return;
                    Thread.Sleep(250);
                    continue;
                }
                var c = client;
                var t = new Thread(() => Serve(c));
                t.IsBackground = true;
                t.Start();
            }
        }

        private void Serve(TcpClient client)
        {
            try
            {
                using (client)
                using (var stream = client.GetStream())
                using (var reader = new StreamReader(stream, new UTF8Encoding(false)))
                using (var writer = new StreamWriter(stream, new UTF8Encoding(false)))
                {
                    writer.AutoFlush = true;
                    string line;
                    while ((line = reader.ReadLine()) != null)
                    {
                        if (line.Trim().Length == 0) continue;
                        string reply = Handle(line);
                        writer.Write(reply);
                        writer.Write('\n');
                    }
                }
            }
            catch (Exception ex)
            {
                Log.Write("conexion cerrada con error: " + ex.Message);
            }
        }

        private string Handle(string line)
        {
            JsonNode id = null;
            try
            {
                var req = JsonNode.Parse(line) as JsonObject;
                if (req == null) return Rpc.Err(null, Rpc.ErrParams, "peticion no es un objeto JSON");
                id = req["id"];
                string method = req["method"]?.GetValue<string>();
                if (string.IsNullOrEmpty(method)) return Rpc.Err(id, Rpc.ErrParams, "falta method");
                var prms = req["params"] as JsonObject ?? new JsonObject();

                Log.Write("-> " + method);

                // Metodos que no necesitan el hilo de la aplicacion
                if (method == "ping")
                    return Rpc.Ok(id, new Dictionary<string, object>
                    {
                        { "puente", "cdcrd-civil3d" },
                        { "version", Handlers.Version },
                        // la version no cambia entre builds: el MVID y la ruta del DLL si
                        { "build", typeof(Handlers).Assembly.ManifestModule.ModuleVersionId.ToString("N").Substring(0, 12) },
                        { "dll", typeof(Handlers).Assembly.Location },
                        { "puerto", Port },
                        { "escritura", AllowWrite },
                        { "comandos", AllowCommands },
                        { "log", Log.Path }
                    });

                if (method == "approval.request")
                {
                    string target = prms["metodo"]?.GetValue<string>();
                    if (string.IsNullOrEmpty(target)) return Rpc.Err(id, Rpc.ErrParams, "falta metodo");
                    var targetParams = prms["parametros"] as JsonObject ?? new JsonObject();
                    string hash = Approvals.Hash(target, targetParams);
                    string token = Approvals.Issue(hash);
                    Log.Write("aprobacion emitida para " + target + " hash " + hash.Substring(0, 12));
                    return Rpc.Ok(id, new Dictionary<string, object> { { "token", token }, { "hash", hash } });
                }

                object result;
                try
                {
                    result = HiloPrincipal.Ejecutar(() => Handlers.Dispatch(method, prms), TimeoutMs);
                }
                catch (BridgeException be)
                {
                    return Rpc.Err(id, be.Code, be.Message);
                }
                catch (Exception ex)
                {
                    Log.Write("error en " + method + ": " + ex);
                    return Rpc.Err(id, Rpc.ErrInternal, ex.GetType().Name + ": " + ex.Message);
                }
                return Rpc.Ok(id, result);
            }
            catch (Exception ex)
            {
                Log.Write("fallo al atender peticion: " + ex);
                return Rpc.Err(id, Rpc.ErrInternal, ex.Message);
            }
        }
    }

    // ExecuteInApplicationContext NO marshala desde un hilo de fondo: solo cambia
    // de contexto de documento a contexto de aplicacion, ambos ya en el hilo
    // principal. Invocado desde el hilo del socket ejecuta el delegado en ESE
    // hilo, y cualquier transaccion o objeto con afinidad de hilo lanza
    // "The calling thread cannot access this object because a different thread
    // owns it" (dialogo modal que cuelga Civil 3D).
    // El evento Application.Idle si corre en el hilo principal y solo dispara
    // cuando Civil 3D no esta en un comando ni en un dialogo, asi que ademas
    // garantiza un momento seguro para abrir transacciones.
    internal static class HiloPrincipal
    {
        private sealed class Tarea
        {
            public Func<object> Fn;
            public object Resultado;
            public Exception Error;
            public readonly ManualResetEventSlim Listo = new ManualResetEventSlim(false);
        }

        private static readonly ConcurrentQueue<Tarea> Cola = new ConcurrentQueue<Tarea>();
        private static int _suscrito;

        public static void Suscribir()
        {
            if (Interlocked.Exchange(ref _suscrito, 1) == 1) return;
            AcApp.Idle += AlEstarInactivo;
            Log.Write("bomba de hilo principal suscrita a Application.Idle");
        }

        public static void Desuscribir()
        {
            if (Interlocked.Exchange(ref _suscrito, 0) == 0) return;
            try { AcApp.Idle -= AlEstarInactivo; } catch { }
        }

        private static void AlEstarInactivo(object sender, EventArgs e)
        {
            Tarea t;
            while (Cola.TryDequeue(out t))
            {
                try { t.Resultado = t.Fn(); }
                catch (Exception ex) { t.Error = ex; }
                finally { t.Listo.Set(); }
            }
        }

        public static object Ejecutar(Func<object> fn, int timeoutMs)
        {
            if (_suscrito == 0)
                throw new BridgeException(Rpc.ErrInternal,
                    "la bomba del hilo principal no esta suscrita: reinicie Civil 3D o escriba CDCRDMCP");
            var t = new Tarea { Fn = fn };
            Cola.Enqueue(t);
            if (!t.Listo.Wait(timeoutMs))
                throw new BridgeException(Rpc.ErrBusy,
                    "Civil 3D no quedo inactivo en " + timeoutMs + " ms: suele estar en un comando, " +
                    "un dialogo modal o en modo edicion. La peticion sigue en cola y se descartara sola");
            if (t.Error != null) throw t.Error;
            return t.Resultado;
        }
    }

    internal class BridgeException : Exception
    {
        public int Code;
        public BridgeException(int code, string message) : base(message) { Code = code; }
    }
}
