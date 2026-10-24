"""Independent Euler spiral oracle using convergent power series, not CAD/Simpson."""
import math


def fresnel(length, radius, full_length):
    a = 1 / (2 * radius * full_length)
    x = sum((-1)**n * a**(2*n) * length**(4*n+1) / (math.factorial(2*n)*(4*n+1)) for n in range(24))
    y = sum((-1)**n * a**(2*n+1) * length**(4*n+3) / (math.factorial(2*n+1)*(4*n+3)) for n in range(24))
    return x, y


class Reference:
    def __init__(self, g):
        self.g = g
        p0, pi, p2 = (g[k] for k in ('inicio','pi','fin'))
        u = [pi[i]-p0[i] for i in range(2)]; v = [p2[i]-pi[i] for i in range(2)]
        self.turn = math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1])
        self.sign = 1 if self.turn > 0 else -1
        self.heading = math.atan2(u[1],u[0])
        self.r = g['radio']; self.li = g['longitud_entrada']; self.lo = g['longitud_salida']
        self.arc = self.r*abs(self.turn)-(self.li+self.lo)/2
        x, y, _, _ = self.curve(self.li+self.arc+self.lo)
        self.trim_out = y/math.sin(abs(self.turn)); self.trim_in = x-self.trim_out*math.cos(abs(self.turn))
        self.ti = math.hypot(*u)-self.trim_in; self.to = math.hypot(*v)-self.trim_out
        self.length = self.ti+self.li+self.arc+self.lo+self.to
        self.breaks = [g['estacion_inicial']+s for s in [0,self.ti,self.ti+self.li,self.ti+self.li+self.arc,self.length-self.to,self.length]]

    def curve(self, s):
        t = min(s,self.li); x,y = fresnel(t,self.r,self.li)
        angle = t*t/(2*self.r*self.li); k=t/(self.r*self.li)
        if s > self.li:
            arc=min(s-self.li,self.arc); begin=self.li/(2*self.r)
            angle=begin+arc/self.r; k=1/self.r
            x+=self.r*(math.sin(angle)-math.sin(begin)); y+=self.r*(math.cos(begin)-math.cos(angle))
        if s > self.li+self.arc:
            t=min(s-self.li-self.arc,self.lo); delta=abs(self.turn)
            full=fresnel(self.lo,self.r,self.lo); remain=fresnel(self.lo-t,self.r,self.lo)
            dx,dy=[a-b for a,b in zip(full,remain)]
            x+=math.cos(delta)*dx+math.sin(delta)*dy
            y+=math.sin(delta)*dx-math.cos(delta)*dy
            angle=delta-(self.lo-t)**2/(2*self.r*self.lo); k=(self.lo-t)/(self.r*self.lo)
        return x,y,angle,k

    def at(self, station, offset=0):
        s=max(0,min(self.length,station-self.g['estacion_inicial']))
        if s <= self.ti: x,y,theta,k=s,0,0,0
        else:
            x,y,theta,k=self.curve(min(s-self.ti,self.li+self.arc+self.lo))
            x+=self.ti; y*=self.sign; theta*=self.sign; k*=self.sign
            if s > self.length-self.to:
                t=s-(self.length-self.to);x+=t*math.cos(self.turn);y+=t*math.sin(self.turn)
        h=self.heading+theta
        return [self.g['inicio'][0]+x*math.cos(self.heading)-y*math.sin(self.heading)+offset*math.sin(h),
                self.g['inicio'][1]+x*math.sin(self.heading)+y*math.cos(self.heading)-offset*math.cos(h)],h,k


def fixture(clockwise=False):
    sign=-1 if clockwise else 1
    y=2100200 if clockwise else 2100020
    return dict(inicio=[620010,y],pi=[620140,y],fin=[620205,y+sign*65*math.sqrt(3)],
                radio=50,longitud_entrada=25,longitud_salida=35,estacion_inicial=100)
