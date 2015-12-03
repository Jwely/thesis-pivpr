__author__ = 'Jwely'

import os

import numpy as np

from py.managers.VecFieldCartesian import VecFieldCartesian
from py.utils import Timer


class MeanVecFieldCartesian:

    def __init__(self, name_tag=None, v3d_paths=None, min_points=20, velocity_fs=None):
        """
        :param v3d_paths:       list of filepaths to v3d files
        :param name_tag:        unique string name tag for this data set
        :param min_points:      minimum number of values for given grid location for statistics to be
                                considered valid. The more points the better, especially for turbulence values.
        :param velocity_fs:     free stream velocity. not really used yet.
        :return:
        """

        self.name_tag = name_tag
        self.v3d_paths = v3d_paths
        self.min_points = min_points
        self.velocity_fs = velocity_fs
        self.constituent_vel_matrix_list = []

        # attributes that will be inherited from the constituent VecField instances
        self.x_set = None
        self.y_set = None
        self.dims = (None, None)
        self.meshgrid = {"x_mesh": None,
                         "y_mesh": None}

        # dictionary of matrices by key symbol. Capitols are averages, lowercase are fluctuations
        self.vel_matrix = {'U': None,       # x direction mean velocity
                           'V': None,       # y direction mean velocity
                           'W': None,       # z direction mean velocity
                           'P': None,       # in-plane velocities (U and V components, not W)
                           'M': None,       # velocity magnitude (all three components)

                           'u': None,       # mean absolute fluctuation in U
                           'v': None,       # mean absolute fluctuation in V
                           'w': None,       # mean absolute fluctuation in W

                           'uu': None,      # turbulent energy in u (u' * u') bar
                           'vv': None,      # turbulent energy in v (v' * v') bar
                           'ww': None,      # turbulent energy in w (w' * w') bar
                           'cte': None,     # total cartesian turbulent energy

                           'uv': None,      # reynolds stress in u/v
                           'uw': None,      # reynolds stress in u/w
                           'vw': None,      # reynolds stress in v/w
                           'uvw': None,     # triple correlation reynolds stress

                           'num': None}     # number of good data points making up stats for other values

        # Build up the data set
        if v3d_paths is not None:
            self.ingest_paths(v3d_paths)    # creates constituent_vel_matrix_list from input filepath list


    def __getitem__(self, key):
        """ allows components of the instance to be accessed more simply through instance[key] """
        if key in self.vel_matrix.keys():
            return self.vel_matrix[key]

        # allows 'uv' to be returned for input key 'vu', which is nice.
        elif key[::-1] in self.vel_matrix.keys():
            return self.vel_matrix[key[::-1]]

        elif key in self.meshgrid.keys():
            return self.meshgrid[key]


    def __setitem__(self, key, value):
        """ allows components of the instance to be set more briefly """
        if key in self.vel_matrix.keys():
            self.vel_matrix[key] = value
        elif key[::-1] in self.vel_matrix.keys():
            self.vel_matrix[key[::-1]] = value
        else:
            raise AttributeError("instance does not accept __setitem__ for '{0}'".format(key))


    def ingest_paths(self, filepath_list):
        """
        Creates VecField3d objects from each filepath in the list
        :param filepath_list:   list of filepaths to ingest
        :param min_points:      grid spaces with fewer than this many good values will be set to no data

        """
        t = Timer()

        # grab the first one and inherit its dimensional information
        first_vf = VecFieldCartesian(filepath_list.pop(0), velocity_fs=self.velocity_fs)
        self.x_set = first_vf.x_set
        self.y_set = first_vf.y_set
        self.dims = first_vf.dims
        self.meshgrid = first_vf.meshgrid
        self.constituent_vel_matrix_list.append(first_vf.vel_matrix)

        for path in filepath_list:
            next_vf = VecFieldCartesian(path, velocity_fs=self.velocity_fs)
            assert next_vf.dims == first_vf.dims, "Inconsistent dimensions detected!"
            self.constituent_vel_matrix_list.append(next_vf.vel_matrix)
        print("loaded {0} files in {1} s".format(len(filepath_list) + 1, t.finish()))

        # now take statistics on the set
        self._average_cartesian(self.min_points)


    def _average_cartesian(self, min_points=None):
        """
        Populates the  U, V, W, u, v, w, uu, vv, ww, uv, uw, and vw  values of the velocity matrix.

        This function is a little mathy, but the principle is to separate the history of values
        into a time averaged mean component, and a time averaged fluctuation component.

        :param min_points:  minimum number of good values in order to consider a cell a good value
        """

        if min_points is not None:
            self.min_points = min_points

        depth = len(self.constituent_vel_matrix_list)
        u_set = np.ma.zeros(self.dims + tuple([depth]))     # u matrix (3d)
        v_set = np.ma.zeros(self.dims + tuple([depth]))     # u matrix (3d)
        w_set = np.ma.zeros(self.dims + tuple([depth]))     # u matrix (3d)
        u_set_p = np.ma.zeros(self.dims + tuple([depth]))   # u fluctuation matrix (3d)
        v_set_p = np.ma.zeros(self.dims + tuple([depth]))   # v fluctuation matrix (3d)
        w_set_p = np.ma.zeros(self.dims + tuple([depth]))   # w fluctuation matrix (3d)

        print("Taking statistics with min_points = {0}".format(min_points))
        for i, cvm in enumerate(self.constituent_vel_matrix_list):
            u_set[:, :, i] = cvm['U']
            v_set[:, :, i] = cvm['V']
            w_set[:, :, i] = cvm['W']

        # build a new mask based on whether or not more data than min_points is available
        mpm = u_set.count(axis=2) <= min_points
        self['num'] = np.ma.masked_array(u_set.count(axis=2), mask=mpm)

        # populate the velocity matrix
        self['U'] = np.ma.masked_array(np.ma.mean(u_set, axis=2), mask=mpm)
        self['V'] = np.ma.masked_array(np.ma.mean(v_set, axis=2), mask=mpm)
        self['W'] = np.ma.masked_array(np.ma.mean(w_set, axis=2), mask=mpm)

        self['M'] = (self['U'] ** 2 + self['V'] ** 2 + self['W'] ** 2) ** 0.5   # magnitudes
        self['P'] = (self['U'] ** 2 + self['V'] ** 2) ** 0.5                    # in plane magnitude (no Z)

        # now subtract out the averages for fluctuation measurements (time averaged)
        for i, cvm in enumerate(self.constituent_vel_matrix_list):
            u_set_p[:, :, i] = u_set[:, :, i] - self['U']
            v_set_p[:, :, i] = v_set[:, :, i] - self['V']
            w_set_p[:, :, i] = w_set[:, :, i] - self['W']

        self['u'] = np.ma.masked_array(np.ma.mean(abs(u_set_p), axis=2), mask=mpm)
        self['v'] = np.ma.masked_array(np.ma.mean(abs(v_set_p), axis=2), mask=mpm)
        self['w'] = np.ma.masked_array(np.ma.mean(abs(w_set_p), axis=2), mask=mpm)

        self['uu'] = np.ma.masked_array(np.ma.mean(u_set_p * u_set_p, axis=2), mask=mpm)
        self['vv'] = np.ma.masked_array(np.ma.mean(v_set_p * v_set_p, axis=2), mask=mpm)
        self['ww'] = np.ma.masked_array(np.ma.mean(w_set_p * w_set_p, axis=2), mask=mpm)
        self['cte'] = (self['uu'] + self['vv'] + self['ww']) / 2

        self['uv'] = np.ma.masked_array(np.ma.mean(u_set_p * v_set_p, axis=2), mask=mpm)
        self['uw'] = np.ma.masked_array(np.ma.mean(u_set_p * w_set_p, axis=2), mask=mpm)
        self['vw'] = np.ma.masked_array(np.ma.mean(v_set_p * w_set_p, axis=2), mask=mpm)
        self['uvw'] = np.ma.masked_array(np.ma.mean(u_set_p * v_set_p * w_set_p, axis=2), mask=mpm)



if __name__ == "__main__":

    directory = "../../data_test"
    paths = [os.path.join(directory, filename) for filename in os.listdir(directory) if filename.endswith(".v3d")]

    mvf = MeanVecFieldCartesian("Station_1", paths[0:5], min_points=3)
    print mvf['u'].count()

