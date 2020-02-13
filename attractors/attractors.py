"""
Support for working with a family of attractor equations (https://en.wikipedia.org/wiki/Attractor#Strange_attractor)

Each attractor has:
- Executable Python code for calculating trajectories, optimized using Numba (numba.pydata.org)
- Readable equations displayable with KaTeX
- Examples of interesting patterns stored in a separate attractors.yml file

Support is provided for reading the attractors.yml file and working with the examples in it.
"""

from collections import OrderedDict

import numpy as np
import pandas as pd
import param
import panel as pn
import inspect
import yaml

from numba import jit
from numpy import sin, cos, sqrt, fabs
from param import concrete_descendents

import numpy.random as npr
npr.seed(12)


@jit(nopython=True)
def trajectory_coords(fn, x0, y0, a, b, c, d, e, f, n):
    """
    Given an attractor fn with up to six parameters a-e, compute n trajectory points
    (starting from x0,y0). Numba-optimized to run at machine-code speeds.
    """
    x, y = np.zeros(n), np.zeros(n)
    x[0], y[0] = x0, y0
    for i in np.arange(n-1):
        x[i+1], y[i+1] = fn(x[i], y[i], a, b, c, d, e, f)
    return x, y


def trajectory(fn, x0, y0, a, b=None, c=None, d=None, e=None, f=None, n=1000000):
    """
    Given an attractor fn with up to six parameters a-e, compute n trajectory points
    (starting from x0,y0) and return as a Pandas dataframe with columns x,y.
    """
    xs, ys = trajectory_coords(fn, x0, y0, a, b, c, d, e, f, n)
    return pd.DataFrame(dict(x=xs,y=ys))



class Attractor(param.Parameterized):
    """Base class for a Parameterized object that can evaluate an attractor trajectory"""
    
    x = param.Number(0,  softbounds=(-2, 2), doc="Starting x value", precedence=-1)
    y = param.Number(0,  softbounds=(-2, 2), doc="Starting y value", precedence=-1)

    a = param.Number(1.7, bounds=(-3, 3), doc="Attractor parameter a")
    b = param.Number(1.7, bounds=(-3, 3), doc="Attractor parameter b")

    colormap = param.ObjectSelector("kgy", precedence=0.7, check_on_set=False,
        doc="Palette of colors to use for plotting",
        objects=['bgy', 'bmw', 'bgyw', 'bmy', 'fire', 'gray', 'kgy', 'kbc', 'viridis', 'inferno'])

    equations = param.List([], class_=str, precedence=-1, readonly=True, doc="""
        LaTeX-formatted list of equations""")
    
    __abstract = True
    
    def __call__(self, n, x=None, y=None):
        """Return a dataframe with *n* points"""
        if x is not None: self.x=x
        if y is not None: self.y=y
        args = [getattr(self,p) for p in self.sig()]
        return trajectory(self.fn, *args, n=n)
    
    def vals(self):
        return [self.__class__.name] + [self.colormap] + [getattr(self,p) for p in self.sig()]

    def sig(self):
        """Returns the calling signature expected by this attractor function"""
        return list(inspect.signature(self.fn).parameters.keys())[:-1]


class FourParamAttractor(Attractor):
    """Base class for most four-parameter attractors"""
    c = param.Number(0.6, softbounds=(-3, 3), doc="Attractor parameter c")
    d = param.Number(1.2, softbounds=(-3, 3), doc="Attractor parameter d")

    __abstract = True


class Clifford(FourParamAttractor):
    equations = param.List([r'$x_{n+1} = \sin\ ay_n + c\ \cos\ ax_n$', 
                            r'$y_{n+1} = \sin\ bx_n + d\ \cos\ by_n$'])
    
    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, c, d, *o):
        return sin(a * y) + c * cos(a * x), \
               sin(b * x) + d * cos(b * y)


class De_Jong(FourParamAttractor):
    equations = param.List([r'$x_{n+1} = \sin\ ay_n - c\ \cos\ bx_n$', 
                            r'$y_{n+1} = \sin\ cx_n - d\ \cos\ dy_n$'])
    
    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, c, d, *o):
        return sin(a * y) - cos(b * x), \
               sin(c * x) - cos(d * y)

    
class Svensson(FourParamAttractor):
    equations = param.List([r'$x_{n+1} = d\ \sin\ ax_n - \sin\ by_n$', 
                            r'$y_{n+1} = c\ \cos\ ax_n + \cos\ by_n$'])
    
    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, c, d, *o):
        return d * sin(a * x) - sin(b * y), \
               c * cos(a * x) + cos(b * y)

    
class Fractal_Dream(Attractor):
    equations = param.List([r'$x_{n+1} = \sin\ by_n + c\ \sin\ bx_n$', 
                            r'$y_{n+1} = \sin\ ax_n + d\ \sin\ ay_n$'])
    
    c = param.Number(1.15, softbounds=(-0.5, 1.5), doc="Attractor parameter c")
    d = param.Number(2.34, softbounds=(-0.5, 1.5), doc="Attractor parameter d")
    
    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, c, d, *o):
        return sin(b*y)+c*sin(b*x), \
               sin(a*x)+d*sin(a*y)

    
class Bedhead(Attractor):
    equations = param.List([r'$x_{n+1} = y_n\ \sin\ \frac{x_ny_n}{b} + \cos(ax_n-y_n)$', 
                            r'$y_{n+1} = x_n+\frac{\sin\ y_n}{b}$'])
    
    a = param.Number(0.64, bounds=(-1, 1))
    b = param.Number(0.76, bounds=(-1, 1))
    
    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, *o):
        return y*sin(x*y/b) + cos(a*x-y), \
               x + sin(y)/b
    
    def __call__(self, n):
        # Avoid interactive divide-by-zero errors for b
        epsilon = 3*np.finfo(float).eps
        if -epsilon < self.b < epsilon:
            self.b = epsilon
        return super(Bedhead,self).__call__(n)

    
class Hopalong1(Attractor):
    equations = param.List([r'$x_{n+1} = y_n-\mathrm{sgn}(x_n)\sqrt{\left|\ bx_n-c\ \right|}$', 
                            r'$y_{n+1} = a-x_n$'])
    
    a = param.Number(9.8, bounds=(0, 10))
    b = param.Number(4.1, bounds=(0, 10))
    c = param.Number(3.8, bounds=(0, 10), doc="Attractor parameter c")

    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, c, *o):
        return y - sqrt(fabs(b * x - c)) * np.sign(x), \
               a - x


class Hopalong2(Hopalong1):
    equations = param.List([r'$x_{n+1} = y_n-1-\mathrm{sgn}(x_n-1)\sqrt{\left|\ bx_n-1-c\ \right|}$', 
                            r'$y_{n+1} = a-x_n-1$'])
    
    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, c, *o):
        return y - 1.0 - sqrt(fabs(b * x - 1.0 - c)) * np.sign(x - 1.0), \
               a - x - 1.0


@jit(nopython=True)
def G(x, mu):
    return mu * x + 2 * (1 - mu) * x**2 / (1.0 + x**2)

class Gumowski_Mira(Attractor):
    equations = param.List([r'$G(x) = \mu x + \frac{2(1-\mu)x^2}{1+x^2}$',
                            r'$x_{n+1} = y_n + ay_n(1-by_n^2) + G(x_n)$', 
                            r'$y_{n+1} = -x_n + G(x_{n+1})$'])
    
    x = param.Number(0,    softbounds=(-20, 20), doc="Starting x value", precedence=0.1)
    y = param.Number(0,    softbounds=(-20, 20), doc="Starting y value", precedence=0.1)
    a = param.Number(0.64, softbounds=( -1,  1))
    b = param.Number(0.76, softbounds=( -1,  1))
    mu = param.Number(0.6, softbounds=( -2,  2), doc="Attractor parameter mu")
    
    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, mu, *o):
        xn = y + a*(1 - b*y**2)*y  +  G(x, mu)
        yn = -x + G(xn, mu)
        return xn, yn


class Symmetric_Icon(Attractor):
    a = param.Number(0.6, softbounds=(-20, 20),  bounds=(None,None), doc="Attractor parameter alpha")
    b = param.Number(1.2, softbounds=(-20, 20),  bounds=(None,None), doc="Attractor parameter beta")
    g = param.Number(0.6, softbounds=(-1,   1),  bounds=(None,None), doc="Attractor parameter gamma")
    om= param.Number(1.2, softbounds=(-0.2, 0.2),bounds=(None,None), doc="Attractor parameter omega")
    l = param.Number(0.6, softbounds=(-3,   3),  bounds=(None,None), doc="Attractor parameter lambda")
    d = param.Number(1.2, softbounds=( 1,  20),  bounds=(None,None), doc="Attractor parameter degree")

    @staticmethod
    @jit(nopython=True)
    def fn(x, y, a, b, g, om, l, d, *o):
        zzbar = x*x + y*y
        p = a*zzbar + l
        zreal, zimag = x, y
    
        for i in range(1, d-1):
            za, zb = zreal * x - zimag * y, zimag * x + zreal * y
            zreal, zimag = za, zb
    
        zn = x*zreal - y*zimag
        p += b*zn
    
        return p*x + g*zreal - om*y, \
               p*y - g*zimag + om*x


class ParameterSets(param.Parameterized):
    """
    Allows selection from sets of pre-defined parameters saved in YAML.
    
    Assumes the YAML file returns a list of groups of values.
    """

    examples_filename = param.Filename("attractors.yml")
    remember_this_one = param.Action(lambda x: x._remember())
    
    load      = param.Action(lambda x: x._load())
    randomize = param.Action(lambda x: x._randomize())
    sort      = param.Action(lambda x: x._sort())
    save      = param.Action(lambda x: x._save(), precedence=0.8)
    example   = param.Selector(objects=[[]], precedence=-1)

    def __init__(self,**params):
        super(ParameterSets,self).__init__(**params)
        self._load()
        
        self.attractors = OrderedDict(sorted([(k,v(name=k + " parameters")) for k,v in concrete_descendents(Attractor).items()]))
        for k in self.attractors:
            self.attractor(k, *self.args(k)[0])

    def _load(self):
        with open(self.examples_filename,"r") as f: 
            vals = yaml.safe_load(f)
            assert(vals and len(vals)>0)
            self.param.example.objects=vals
            self.example = vals[0]

    def _save(self):
        with open(self.examples_filename,"w") as f: 
            yaml.dump(self.param.example.objects,f)

    def __call__(self):        return self.example
    def _randomize(self):      npr.shuffle(self.param.example.objects)
    def _sort(self):            self.param.example.objects = list(sorted(self.param.example.objects))
    def _add_item(self, item): self.param.example.objects += [item] ; self.example=item
    def _remember(self):
        vals = ats.attractor_type.vals() # forward reference
        self._add_item(vals)
        
    def args(self, name):
        return [v[1:] for v in self.param.example.objects if v[0]==name]

    def attractor(self, name, *args):
        """Factory function to return an Attractor object with the given name and arg values"""
        attractor = self.attractors[name]
        fn_params = ['colormap'] + attractor.sig()
        attractor.param.set_param(**dict(zip(fn_params, args)))
        return attractor
