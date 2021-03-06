"""
2D polynomial trends.
"""
import numpy as np
from sklearn.utils.validation import check_is_fitted
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression

from .base import BaseGridder, check_fit_input
from .coordinates import get_region


class Trend(BaseGridder):
    """
    Fit a 2D polynomial trend to spatial data.

    The trend is estimated through weighted least-squares regression.

    The Jacobian (design, sensitivity, feature, etc) matrix for the regression
    is normalized using :class:`sklearn.preprocessing.StandardScaler` without
    centering the mean so that the transformation can be undone in the
    estimated coefficients.

    Parameters
    ----------
    degree : int
        The degree of the polynomial. Must be >= 1.

    Attributes
    ----------
    coef_ : array
        The estimated polynomial coefficients that fit the observed data.
    region_ : tuple
        The boundaries (``[W, E, S, N]``) of the data used to fit the
        interpolator. Used as the default region for the
        :meth:`~verde.Trend.grid` and :meth:`~verde.Trend.scatter` methods.
    residual_ : array
        The difference between the input data and the predicted polynomial
        trend.

    Examples
    --------

    >>> from verde import grid_coordinates
    >>> coordinates = grid_coordinates((1, 5, -5, -1), shape=(5, 5))
    >>> data = 10 + 2*coordinates[0] - 0.4*coordinates[1]
    >>> trend = Trend(degree=1).fit(coordinates, data)
    >>> print(', '.join(['{:.1f}'.format(i) for i in trend.coef_]))
    10.0, 2.0, -0.4
    >>> import numpy as np
    >>> np.allclose(trend.predict(coordinates), data)
    True
    >>> np.allclose(trend.residual_, 0, atol=1e-5)
    True
    >>> # Use weights to account for outliers
    >>> data_out = data.copy()
    >>> data_out[2, 2] += 500
    >>> weights = np.ones_like(data)
    >>> weights[2, 2] = 1e-10
    >>> trend_out = Trend(degree=1).fit(coordinates, data_out, weights)
    >>> print(', '.join(['{:.1f}'.format(i) for i in trend_out.coef_]))
    10.0, 2.0, -0.4
    >>> print('{:.2f}'.format(trend_out.residual_[2, 2]))
    500.00

    See also
    --------
    verde.trend_jacobian : Make the Jacobian matrix for 2D polynomial
    verde.VectorTrend : Polynomial trend estimator for multi-component data

    """

    def __init__(self, degree):
        self.degree = degree

    def fit(self, coordinates, data, weights=None):
        """
        Fit the trend to the given data.

        The data region is captured and used as default for the
        :meth:`~verde.Trend.grid` and :meth:`~verde.Trend.scatter` methods.

        All input arrays must have the same shape.

        Parameters
        ----------
        coordinates : tuple of arrays
            Arrays with the coordinates of each data point. Should be in the
            following order: (easting, northing, vertical, ...). Only easting
            and northing will be used, all subsequent coordinates will be
            ignored.
        data : array
            The data values of each data point.
        weights : None or array
            If not None, then the weights assigned to each data point.
            Typically, this should be 1 over the data uncertainty squared.

        Returns
        -------
        self
            Returns this estimator instance for chaining operations.

        """
        coordinates, data, weights = check_fit_input(coordinates, data, weights)
        self.region_ = get_region(coordinates[:2])
        jac = trend_jacobian(coordinates[:2], degree=self.degree, dtype=data.dtype)
        scaler = StandardScaler(copy=False, with_mean=False, with_std=True)
        jac = scaler.fit_transform(jac)
        regr = LinearRegression(fit_intercept=False, normalize=False)
        regr.fit(jac, data.ravel(), sample_weight=weights)
        self.residual_ = data - jac.dot(regr.coef_).reshape(data.shape)
        self.coef_ = regr.coef_ / scaler.scale_
        return self

    def predict(self, coordinates):
        """
        Evaluate the polynomial trend on the given set of points.

        Requires a fitted estimator (see :meth:`~verde.Trend.fit`).

        Parameters
        ----------
        coordinates : tuple of arrays
            Arrays with the coordinates of each data point. Should be in the
            following order: (easting, northing, vertical, ...). Only easting
            and northing will be used, all subsequent coordinates will be
            ignored.

        Returns
        -------
        data : array
            The trend values evaluated on the given points.

        """
        check_is_fitted(self, ["coef_"])
        jac = trend_jacobian(coordinates[:2], degree=self.degree)
        shape = np.broadcast(*coordinates[:2]).shape
        return jac.dot(self.coef_).reshape(shape)


def polynomial_power_combinations(degree):
    """
    Combinations of powers for a 2D polynomial of a given degree.

    Produces the (i, j) pairs to evaluate the polynomial with ``x**i*y**j``.

    Parameters
    ----------
    degree : int
        The degree of the 2D polynomial. Must be >= 1.

    Returns
    -------
    combinations : tuple
        A tuple with ``(i, j)`` pairs.

    Examples
    --------

    >>> print(polynomial_power_combinations(1))
    ((0, 0), (1, 0), (0, 1))
    >>> print(polynomial_power_combinations(2))
    ((0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2))
    >>> # This is a long polynomial so split it in two lines
    >>> print(" ".join([str(c) for c in polynomial_power_combinations(3)]))
    (0, 0) (1, 0) (0, 1) (2, 0) (1, 1) (0, 2) (3, 0) (2, 1) (1, 2) (0, 3)

    """
    if degree < 1:
        raise ValueError("Invalid polynomial degree '{}'. Must be >= 1.".format(degree))
    combinations = ((i, j) for j in range(degree + 1) for i in range(degree + 1 - j))
    return tuple(sorted(combinations, key=sum))


def trend_jacobian(coordinates, degree, dtype="float64"):
    """
    Make the Jacobian for a 2D polynomial of the given degree.

    Each column of the Jacobian is ``easting**i * northing**j`` for each (i, j)
    pair in the polynomial of the given degree.

    Parameters
    ----------
    coordinates : tuple of arrays
        Arrays with the coordinates of each data point. Should be in the
        following order: (easting, northing, vertical, ...). Only easting and
        northing will be used, all subsequent coordinates will be ignored.
    degree : int
        The degree of the 2D polynomial. Must be >= 1.
    dtype : str or numpy dtype
        The type of the output Jacobian numpy array.

    Returns
    -------
    jacobian : 2D array
        The (n_data, n_coefficients) Jacobian matrix.

    Examples
    --------

    >>> import numpy as np
    >>> east = np.linspace(0, 4, 5)
    >>> north = np.linspace(-5, -1, 5)
    >>> print(trend_jacobian((east, north), degree=1, dtype=np.int))
    [[ 1  0 -5]
     [ 1  1 -4]
     [ 1  2 -3]
     [ 1  3 -2]
     [ 1  4 -1]]
    >>> print(trend_jacobian((east, north), degree=2, dtype=np.int))
    [[ 1  0 -5  0  0 25]
     [ 1  1 -4  1 -4 16]
     [ 1  2 -3  4 -6  9]
     [ 1  3 -2  9 -6  4]
     [ 1  4 -1 16 -4  1]]

    See also
    --------
    verde.Trend : Polynomial trend estimator
    verde.VectorTrend : Polynomial trend estimator for multi-component data

    """
    easting, northing = coordinates[:2]
    if easting.shape != northing.shape:
        raise ValueError("Coordinate arrays must have the same shape.")
    combinations = polynomial_power_combinations(degree)
    ndata = easting.size
    nparams = len(combinations)
    out = np.empty((ndata, nparams), dtype=dtype)
    for col, (i, j) in enumerate(combinations):
        out[:, col] = (easting.ravel() ** i) * (northing.ravel() ** j)
    return out


class VectorTrend(BaseGridder):
    """
    Fit 2D polynomial trends to multi-component vector data.

    Each data component is fitted to a separated :class:`verde.Trend`. The
    trends can be evaluated separately through the ``VectorTrend.component_``
    attribute or jointly using the methods of this class.

    Parameters
    ----------
    degree : int
        The degree of the polynomials. Must be >= 1.

    Attributes
    ----------
    component_ : list
        List of the fitted :class:`verde.Trend` on each component of the data.
    region_ : tuple
        The boundaries (``[W, E, S, N]``) of the data used to fit the
        interpolator. Used as the default region for the
        :meth:`~verde.Trend.grid` and :meth:`~verde.Trend.scatter` methods.
    residual_ : list of array
        The difference between each component of the input data and the
        predicted polynomial trend.

    See also
    --------
    verde.Trend : Polynomial trend estimator
    verde.trend_jacobian : Make the Jacobian matrix for 2D polynomial

    """

    def __init__(self, degree):
        self.degree = degree

    def fit(self, coordinates, data, weights=None):
        """
        Fit the trend to the given multi-component data.

        The data region is captured and used as default for the
        :meth:`~verde.VectorTrend.grid` and :meth:`~verde.VectorTrend.scatter`
        methods.

        All input arrays must have the same shape. If weights are given, there
        must be a separate array for each component of the data.

        Parameters
        ----------
        coordinates : tuple of arrays
            Arrays with the coordinates of each data point. Should be in the
            following order: (easting, northing, vertical, ...). Only easting
            and northing will be used, all subsequent coordinates will be
            ignored.
        data : tuple of array
            The data values of each component at each data point. Must be a
            tuple.
        weights : None or tuple of array
            If not None, then the weights assigned to each data point of each
            data component. Typically, this should be 1 over the data
            uncertainty squared.

        Returns
        -------
        self
            Returns this estimator instance for chaining operations.

        """
        if not isinstance(data, tuple):
            raise ValueError(
                "Data must be a tuple of arrays. {} given.".format(type(data))
            )
        if weights is not None and not isinstance(weights, tuple):
            raise ValueError(
                "Weights must be a tuple of arrays. {} given.".format(type(weights))
            )
        coordinates, data, weights = check_fit_input(coordinates, data, weights)
        self.region_ = get_region(coordinates[:2])
        self.component_ = [
            Trend(degree=self.degree).fit(coordinates, data_comp, weight_comp)
            for data_comp, weight_comp in zip(data, weights)
        ]
        self.residual_ = tuple(
            data_comp - comp.predict(coordinates).reshape(data_comp.shape)
            for data_comp, comp in zip(data, self.component_)
        )
        return self

    def predict(self, coordinates):
        """
        Evaluate the polynomial trend of each component on a of points.

        Requires a fitted estimator (see :meth:`~verde.VectorTrend.fit`).

        Parameters
        ----------
        coordinates : tuple of arrays
            Arrays with the coordinates of each data point. Should be in the
            following order: (easting, northing, vertical, ...). Only easting
            and northing will be used, all subsequent coordinates will be
            ignored.

        Returns
        -------
        data : tuple of array
            The trend values for each vector component evaluated on the given
            points. The order of components will be the same as was provided to
            :meth:`~verde.VectorTrend.fit`.

        """
        check_is_fitted(self, ["component_"])
        return tuple(comp.predict(coordinates) for comp in self.component_)
