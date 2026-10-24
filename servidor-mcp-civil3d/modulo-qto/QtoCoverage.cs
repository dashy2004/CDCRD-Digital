using System;
using System.Collections.Generic;
using System.Linq;
namespace Cdcrd.Qto;

// Union of the sample segment portions covered by visible TIN triangles.
// Uses local coordinate differences to avoid loss from large eastings/northings.
internal static class QtoCoverage
{
 internal static bool Covers(double[] a,double[] b,IEnumerable<double[][]> triangles)
 {
  double dx=b[0]-a[0],dy=b[1]-a[1];
  if(!double.IsFinite(dx)||!double.IsFinite(dy)||dx*dx+dy*dy<1e-12)throw new ArgumentException("Invalid sample segment");
  var spans=new List<(double Lo,double Hi)>();
  foreach(var t in triangles)
  {
   double cross=(t[1][0]-t[0][0])*(t[2][1]-t[0][1])-(t[1][1]-t[0][1])*(t[2][0]-t[0][0]);
   if(!double.IsFinite(cross)||Math.Abs(cross)<1e-12)continue;
   double sign=Math.Sign(cross),lo=0,hi=1;bool hit=true;
   for(int i=0;i<3;i++)
   {
    var u=t[i];var v=t[(i+1)%3];double ex=v[0]-u[0],ey=v[1]-u[1];
    double at=sign*(ex*(a[1]-u[1])-ey*(a[0]-u[0])),delta=sign*(ex*dy-ey*dx);
    double tolerance=1e-8*Math.Max(1,Math.Sqrt(ex*ex+ey*ey));
    if(Math.Abs(delta)<1e-14){if(at < -tolerance){hit=false;break;}continue;}
    double limit=(-tolerance-at)/delta;
    if(delta>0)lo=Math.Max(lo,limit);else hi=Math.Min(hi,limit);
    if(lo>hi){hit=false;break;}
   }
   if(hit)spans.Add((lo,hi));
  }
  double end=0;
  foreach(var span in spans.OrderBy(s=>s.Lo)){if(span.Hi<end)continue;if(span.Lo>end+1e-8)return false;end=Math.Max(end,span.Hi);if(end>=1-1e-8)return true;}
  return false;
 }
}
