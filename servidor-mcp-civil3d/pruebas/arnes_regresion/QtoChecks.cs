using Cdcrd.Qto;
static class QtoChecks
{
 internal static void Run(Action<bool,string> check)
 {
  double[][][] Rect(double x0,double x1,double y0=0,double y1=20)=>new[]{new[]{new[]{x0,y0},new[]{x1,y0},new[]{x1,y1}},new[]{new[]{x0,y0},new[]{x1,y1},new[]{x0,y1}}};
  var square=Rect(0,40);
  check(QtoCoverage.Covers(new[]{20d,0},new[]{20d,20},square),"QTO complete cross-section");
  check(QtoCoverage.Covers(new[]{0d,0},new[]{0d,20},square),"QTO exact boundary");
  check(QtoCoverage.Covers(new[]{40d,20},new[]{40d,0},square),"QTO reversed boundary");
  check(QtoCoverage.Covers(new[]{0d,0},new[]{40d,20},square),"QTO internal diagonal");
  check(!QtoCoverage.Covers(new[]{20d,-1},new[]{20d,20},square),"QTO partial coverage rejected");
  check(!QtoCoverage.Covers(new[]{20d,-1},new[]{20d,21},square),"QTO both ends outside rejected");
  check(!QtoCoverage.Covers(new[]{-1d,0},new[]{-1d,20},square),"QTO outside parallel edge rejected");
  var hole=Rect(0,40,0,8).Concat(Rect(0,40,12,20));
  check(!QtoCoverage.Covers(new[]{20d,0},new[]{20d,20},hole),"QTO internal hole rejected");
  var gap=Rect(0,40,0,10).Concat(Rect(0,40,10.0001,20));
  check(!QtoCoverage.Covers(new[]{20d,0},new[]{20d,20},gap),"QTO small physical gap rejected");
  var shifted=square.Select(t=>t.Reverse().Select(p=>new[]{p[0]+620500,p[1]+2100000}).ToArray());
  check(QtoCoverage.Covers(new[]{620520d,2100000},new[]{620520d,2100020},shifted),"QTO large coordinates and reversed triangles");
  check(!QtoCoverage.Covers(new[]{0d,0},new[]{1d,1},Array.Empty<double[][]>()),"QTO no triangles rejected");
  check(!QtoCoverage.Covers(new[]{0d,0},new[]{1d,1},new[]{new[]{new[]{0d,0},new[]{1d,1},new[]{2d,2}}}),"QTO degenerate triangle rejected");
  bool invalid=false;try{QtoCoverage.Covers(new[]{0d,0},new[]{0d,0},square);}catch(ArgumentException){invalid=true;}check(invalid,"QTO zero length rejected");
 }
}
