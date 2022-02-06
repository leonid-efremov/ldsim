"""
Classes for defining laser diode vertical (epitaxial) and lateral design.
"""

import numpy as np
from ldsim import constants as const, units


params = ('Ev', 'Ec', 'Nd', 'Na', 'Nc', 'Nv', 'mu_n', 'mu_p', 'tau_n',
          'tau_p', 'B', 'Cn', 'Cp', 'eps', 'n_refr', 'Eg', 'C_dop',
          'fca_e', 'fca_h')
params_active = ('g0', 'N_tr')


class Layer:
    def __init__(self, name, thickness, active=False):
        """
        Semiconductor diode layer.

        Parameters
        ----------
            name : str
                Layer name.
            thickness : float
                Layer thickness (cm).
            active : bool
                Whether layer is a part of active region, i.e. takes part
                in stimulated light emission.

        """
        self.name = name
        self.dx = thickness
        self.active = active

        # initialize `dct_x` and `dct_z`, that store spatial dependencies of all
        # the parameters as lists of polynomial coefficients
        self.dct_x = dict.fromkeys(params, [np.nan])
        self.dct_x['C_dop'] = self.dct_x['Nd'] = self.dct_x['Na'] = [0.0]
        self.dct_z = dict.fromkeys(params, [])
        self.dct_z['C_dop'] = self.dct_z['Nd'] = self.dct_z['Na'] = []
        if active:
            self.dct_x.update(dict.fromkeys(params_active, [np.nan]))
            self.dct_z.update(dict.fromkeys(params_active, [1.0]))

    def __repr__(self):
        s1 = 'Layer \"{}\"'.format(self.name)
        s2 = '{} um'.format(self.dx * 1e4)
        Cdop = self.calculate('C_dop', [0, self.dx])
        if Cdop[0] > 0 and Cdop[1] > 0:
            s3 = 'n-type'
        elif Cdop[0] < 0 and Cdop[1] < 0:
            s3 = 'p-type'
        else:
            s3 = 'i-type'
        if self.active:
            s4 = 'active'
        else:
            s4 = 'not active'
        return ' / '.join((s1, s2, s3, s4))

    def __str__(self):
        return self.name

    def _choose_dict(self, axis):
        if axis == 'x':
            return self.dct_x
        elif axis == 'z':
            return self.dct_z
        raise ValueError(f'Unknown axis {axis}.')

    def get_thickness(self):
        return self.dx

    def calculate(self, param, x, z=0.0):
        "Calculate value of parameter `param` at location (`x`, `z`)."
        p_x = self.dct_x[param]
        p_z = self.dct_z[param]
        return np.polyval(p_x, x) + np.polyval(p_z + [0.0], z)

    def update(self, d, axis='x'):
        "Update polynomial coefficients of parameters."
        # check input
        assert isinstance(d, dict)
        dct = self._choose_dict(axis)

        # update dictionary values
        for k, v in d.items():
            if k not in self.dct_x:
                raise Exception(f'Unknown parameter {k}')
            if isinstance(v, (int, float)):
                dct[k] = [v]
            else:
                dct[k] = v
        if 'Ec' in d or 'Ev' in d:
            self._update_Eg(axis)
        if 'Nd' in d or 'Na' in d:
            self._update_Cdop(axis)

    def _update_Eg(self, axis):
        dct = self._choose_dict(axis)
        p_Ec = dct['Ec']
        p_Ev = dct['Ev']
        delta = len(p_Ec) - len(p_Ev)
        if delta > 0:
            p_Ev = [0.0] * delta + p_Ev
        elif delta < 0:
            p_Ec = [0.0] * (-delta) + p_Ec
        dct['Eg'] = [Ec - Ev for Ec, Ev in zip(p_Ec, p_Ev)]

    def _update_Cdop(self, axis):
        dct = self._choose_dict(axis)
        p_Nd = dct['Nd']
        p_Na = dct['Na']
        delta = len(p_Nd) - len(p_Na)
        if delta > 0:
            p_Na = [0.0] * delta + p_Na
        elif delta < 0:
            p_Nd = [0.0] * (-delta) + p_Nd
        dct['C_dop'] = [Nd - Na for Nd, Na in zip(p_Nd, p_Na)]

    def make_gradient_layer(self, other, name, thickness, active=False, deg=1):
        """
        Create a layer where all parameters gradually change from their
        endvalues in the current layer to values in `other` at x = 0.
        By default all parameters change linearly, this can be change by
        increasing polynomial degree `deg`.
        """
        layer_new = Layer(name, thickness, active=active)
        x = np.array([0, thickness])
        y = np.zeros(2)
        for key in self.d:
            y[0] = self.calculate(key, self.dx)
            y[1] = other.calculate(key, 0)
            p = np.polyfit(x=x, y=y, deg=deg)
            layer_new.update({key: p}, axis='x')
        layer_new.update(self.dct_z, axis='z')  # same f(z) as in current layer
        return layer_new


class LaserDiode:
    def __init__(self, layers, L, w, R1, R2, lam, ng, alpha_i, beta_sp):
        """
        Class for storing laser diode parameters.

        Parameters
        ----------
        layers : list
            Layers that compose the diode (`Layer` objects).
        L : number
            Resonator length (cm).
        w : number
            Stripe width (cm).
        R1 : float
            Back (x=0) mirror reflectivity (0<`R1`<=1).
        R2 : float
            Front (x=L) mirror reflectivity (0<`R2`<=1).
        lam : number
            Operating wavelength.
        ng : number
            Group refractive index.
        alpha_i : number
            Internal optical loss (cm-1). Should not include free carrier
            absorption.
        beta_sp : number
            Spontaneous emission factor, i.e. the fraction of spontaneous
            emission that is coupled with the lasing mode.
 
        """
        # copy inputs
        assert all(isinstance(layer, Layer) for layer in layers)
        self.layers = list(layers)
        self.L = L
        self.w = w
        assert 0 < R1 <= 1 and 0 < R2 <= 1
        self.R1 = R1
        self.R2 = R2
        self.lam = lam
        self.ng = ng
        self.alpha_i = alpha_i
        self.beta_sp = beta_sp

        # additinal attributes
        self.alpha_m = 1 / (2 * L) * np.log(1 / (R1 * R2))
        self.photon_energy = const.h * const.c / lam
        self.is_dimensionless = False

    def make_dimensionless(self):
        "Make every parameter dimensionless."
        if self.is_dimensionless:
            return
        self.L /= units.x
        self.w /= units.x
        self.lam /= units.x
        self.alpha_i /= 1 / units.x
        self.alpha_m /= 1 / units.x
        self.photon_energy /= units.E
        self.is_dimensionless = True

    def original_units(self):
        "Convert all values back to original units."
        if not self.is_dimensionless:
            return
        self.L *= units.x
        self.w *= units.x
        self.lam *= units.x
        self.alpha_i *= 1 / units.x
        self.alpha_m *= 1 / units.x
        self.photon_energy *= units.E
        self.is_dimensionless = False

    def get_boundaries(self):
        "Get an array of layer boundaries."
        return np.cumsum([0.0] + [layer.get_thickness()
                                  for layer in self.layers])

    def get_thickness(self):
        "Get sum of all layers' thicknesses."
        return self.get_boundaries()[-1]

    def set_length(self, L):
        "Change laser diode length (cm)."
        scale = L / self.L
        self.L = L
        for layer in self.layers:
            for k, v in layer.dct_z:
                layer.dct_z[k] = [vi / scale for vi in v[:-1]] +[v[-1]]

    def _ind_dx(self, x):
        "Global `x` coordinate -> (Layer index, local `x`)"
        if x == 0:
            return 0, 0.0
        xi = 0.0
        for i, layer in enumerate(self.layers):
            if x <= (xi + layer.dx):
                return i, x - xi
            xi += layer.dx
        return np.nan, np.nan

    def _inds_dx(self, x):
        "Apply `_ind_dx` to every point in array `x`."
        # flatten x if needed
        reshape = False
        if x.ndim > 1:
            reshape = True
            shape = x.shape
            x = x.flatten()

        # find layer indices and relative coordinate values
        inds = np.zeros_like(x)
        dx = np.zeros_like(x)
        for i, xi in enumerate(x):
            inds[i], dx[i] = self._ind_dx(xi)

        if reshape:  # reshape arrays if needed
            inds = inds.reshape(shape)
            dx = dx.reshape(shape)
        return inds, dx

    def calculate(self, param, x, z=0.0, inds=None, dx=None):
        "Calculate values of `param` at locations (`x`, `z`)."
        val = np.zeros_like(x)
        if isinstance(x, (float, int)):
            ind, dx = self._ind_dx(x)
            return self.layers[ind].calculate(param, dx, z)
        else:
            if inds is None or dx is None:
                inds, dx = self._inds_dx(x)
            for i, layer in enumerate(self.layers):
                ix = (inds == i)
                if ix.any():
                    val[ix] = layer.calculate(param, dx[ix], z)
        return val
