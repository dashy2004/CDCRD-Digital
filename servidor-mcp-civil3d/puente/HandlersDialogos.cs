using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;
using AcadApp=Autodesk.AutoCAD.ApplicationServices.Application;
namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        [DllImport("user32.dll")] private static extern bool IsWindowEnabled(IntPtr hWnd);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
        [DllImport("user32.dll")] private static extern bool EnumThreadWindows(uint threadId, EnumThreadDelegate fn, IntPtr lp);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr h, StringBuilder sb, int max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr h, StringBuilder sb, int max);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
        [DllImport("user32.dll")] private static extern bool EnumWindows(EnumThreadDelegate fn, IntPtr lp);
        [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr parent, EnumThreadDelegate fn, IntPtr lp);
        private delegate bool EnumThreadDelegate(IntPtr hWnd, IntPtr lParam);

        // Handle de la ventana principal, capturado en el hilo principal al
        // inicializar (AcadApp.MainWindow no se toca desde el hilo del socket).
        internal static IntPtr HandlePrincipal = IntPtr.Zero;

        internal static void CapturarHandlePrincipal()
        {
            try { HandlePrincipal = AcadApp.MainWindow.Handle; } catch { }
        }

        private static object DiagDialogos(JsonObject p) { return DiagDialogosSinHilo(); }

        // Servido desde el hilo del socket (0.5.2): solo user32, sin API de AutoCAD,
        // asi responde aunque un modal tenga bloqueada la bomba de Idle. Para cada
        // dialogo clasico (#32770) devuelve tambien sus textos estaticos: el mensaje
        // de un MessageBox queda como evidencia sin captura de pantalla.
        internal static object DiagDialogosSinHilo()
        {
            IntPtr hMain = HandlePrincipal;
            if (hMain == IntPtr.Zero)
                try { hMain = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle; } catch { }
            bool mainHabilitada = hMain != IntPtr.Zero && IsWindowEnabled(hMain);
            uint pidPropio = (uint)System.Diagnostics.Process.GetCurrentProcess().Id;
            var ventanas = new List<object>();
            EnumWindows((h, lp) =>
            {
                if (!IsWindowVisible(h) || h == hMain) return true;
                GetWindowThreadProcessId(h, out uint pid);
                if (pid != pidPropio) return true;
                var titulo = new StringBuilder(256); GetWindowText(h, titulo, 256);
                var clase = new StringBuilder(128); GetClassName(h, clase, 128);
                var cl = clase.ToString();
                // los dialogos modales clasicos de AutoCAD/WPF/WinForms
                if (cl == "#32770" || cl.StartsWith("WindowsForms10") || cl.StartsWith("HwndWrapper"))
                {
                    var v = new Dictionary<string, object> { { "titulo", titulo.ToString() }, { "clase", cl },
                        { "habilitada", IsWindowEnabled(h) } };
                    if (cl == "#32770")
                    {
                        var textos = new List<string>();
                        EnumChildWindows(h, (hc, lc) =>
                        {
                            var cc = new StringBuilder(64); GetClassName(hc, cc, 64);
                            var c = cc.ToString();
                            if (c == "Static" || c == "Button" || c == "DirectUIHWND")
                            {
                                var tx = new StringBuilder(1024); GetWindowText(hc, tx, 1024);
                                if (tx.Length > 0 && textos.Count < 20) textos.Add(tx.ToString());
                            }
                            return true;
                        }, IntPtr.Zero);
                        v["textos"] = textos;
                    }
                    ventanas.Add(v);
                }
                return true;
            }, IntPtr.Zero);
            return new Dictionary<string, object>
            {
                { "modal_abierto", !mainHabilitada },
                { "ventana_principal_habilitada", mainHabilitada },
                { "ventanas", ventanas },
                { "hilo", "socket" },
                { "nota", "modal_abierto=true significa que un dialogo bloquea Civil 3D y las peticiones al puente van a vencer por timeout" }
            };
        }
    }
}
