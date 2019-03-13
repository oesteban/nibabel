# emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the NiBabel package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
''' Linear transforms '''
from __future__ import division, print_function, absolute_import
import h5py
import numpy as np
from scipy import ndimage as ndi

from .base import ImageSpace, TransformBase
from ..funcs import four_to_three


class Affine(TransformBase):
    '''Represents linear transforms on image data'''
    __slots__ = ['_matrix']

    def __init__(self, matrix):
        '''Initialize a transform

        Parameters
        ----------

        matrix : ndarray
            The inverse coordinate transformation matrix **in physical
            coordinates**, mapping coordinates from *reference* space
            into *moving* space.
            This matrix should be provided in homogeneous coordinates.

        Examples
        --------

        >>> xfm = Affine([[1, 0, 0, 4], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        >>> xfm.matrix  # doctest: +NORMALIZE_WHITESPACE
        array([[1, 0, 0, 4],
               [0, 1, 0, 0],
               [0, 0, 1, 0],
               [0, 0, 0, 1]])

        '''
        self._matrix = np.array(matrix)
        assert self._matrix.ndim in (2, 3), 'affine matrix should be 2D or 3D'
        assert self._matrix.shape[0] == self._matrix.shape[1], 'affine matrix is not square'
        super(Affine, self).__init__()

    @property
    def matrix(self):
        return self._matrix

    def resample(self, moving, order=3, mode='constant', cval=0.0, prefilter=True,
                 output_dtype=None):
        '''Resample the moving image in reference space

        Parameters
        ----------

        moving : `spatialimage`
            The image object containing the data to be resampled in reference
            space
        order : int, optional
            The order of the spline interpolation, default is 3.
            The order has to be in the range 0-5.
        mode : {'reflect', 'constant', 'nearest', 'mirror', 'wrap'}, optional
            Determines how the input image is extended when the resamplings overflows
            a border. Default is 'constant'.
        cval : float, optional
            Constant value for ``mode='constant'``. Default is 0.0.
        prefilter: bool, optional
            Determines if the moving image's data array is prefiltered with
            a spline filter before interpolation. The default is ``True``,
            which will create a temporary *float64* array of filtered values
            if *order > 1*. If setting this to ``False``, the output will be
            slightly blurred if *order > 1*, unless the input is prefiltered,
            i.e. it is the result of calling the spline filter on the original
            input.

        Returns
        -------

        moved_image : `spatialimage`
            The moving imaged after resampling to reference space.


        Examples
        --------

        >>> import nibabel as nib
        >>> xfm = Affine([[1, 0, 0, 4], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        >>> ref = nib.load('image.nii.gz')
        >>> xfm.reference = ref
        >>> xfm.resample(ref, order=0)

        '''
        if output_dtype is None:
            output_dtype = moving.header.get_data_dtype()

        try:
            reference = self.reference
        except ValueError:
            print('Warning: no reference space defined, using moving as reference')
            reference = moving

        # Compose an index to index affine matrix
        matrix = reference.affine.dot(self._matrix.dot(np.linalg.inv(moving.affine)))
        mdata = moving.get_data()
        moved = ndi.affine_transform(
            mdata, matrix=matrix[:mdata.ndim, :mdata.ndim],
            offset=matrix[:mdata.ndim, mdata.ndim],
            output_shape=reference.shape, order=order, mode=mode,
            cval=cval, prefilter=prefilter)

        moved_image = moving.__class__(moved, reference.affine, moving.header)
        moved_image.header.set_data_dtype(output_dtype)

        return moved_image

    def map_point(self, coords, forward=True):
        coords = np.array(coords)
        if coords.shape[0] == self._matrix.shape[0] - 1:
            coords = np.append(coords, [1])
        affine = self._matrix if forward else np.linalg.inv(self._matrix)
        return affine.dot(coords)[:-1]

    def map_voxel(self, index, moving=None):
        try:
            reference = self.reference
        except ValueError:
            print('Warning: no reference space defined, using moving as reference')
            reference = moving
        else:
            if moving is None:
                moving = reference
        finally:
            if reference is None:
                raise ValueError('Reference and moving spaces are both undefined')

        index = np.array(index)
        if index.shape[0] == self._matrix.shape[0] - 1:
            index = np.append(index, [1])

        matrix = reference.affine.dot(self._matrix.dot(np.linalg.inv(moving.affine)))
        return tuple(matrix.dot(index)[:-1])

    def to_filename(self, filename):
        '''Store the transform in BIDS-Transforms HDF5 file format (.x5).
        '''
        with h5py.File(filename, 'w') as out_file:
            root = out_file.create_group('/0')
            root.create_dataset('/0/Transform', data=self._matrix[:3, :])
            root.create_dataset('/0/Inverse', data=np.linalg.inv(self._matrix)[:3, :])
            root['Type'] = 'affine'

            if self._reference:
                refgrp = root.create_group('/0/Reference')
                refgrp.create_dataset('/0/Reference/vox2ras', data=self.reference.affine)
                refgrp.create_dataset('/0/Reference/ras2vox', data=self.reference.inverse)
                refgrp.create_dataset('/0/Reference/shape', data=self.reference.shape)
                refgrp.create_dataset('/0/Reference/ndim', data=self.reference.ndim)
                refgrp['Type'] = 'image'

        return filename
